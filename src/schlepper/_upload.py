"""Asset upload flow for Cloudflare Pages."""

from __future__ import annotations

import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from schlepper._auth import is_jwt_expired
from schlepper._client import CloudflareClient
from schlepper._constants import (
    BULK_UPLOAD_CONCURRENCY,
    MAX_BUCKET_FILE_COUNT,
    MAX_BUCKET_SIZE,
    MAX_CHECK_MISSING_ATTEMPTS,
    MAX_UPLOAD_ATTEMPTS,
)
from schlepper._errors import APIError, UploadError
from schlepper._types import FileEntry

logger = logging.getLogger("schlepper")


def _build_buckets(files: list[FileEntry]) -> list[list[FileEntry]]:
    """Distribute *files* into upload buckets.

    Files are sorted largest-first, then each file is placed into the first
    bucket that can fit it (by both size and count limits).  If no existing
    bucket can fit the file, a new bucket is created.
    """
    sorted_files = sorted(files, key=lambda f: f.size, reverse=True)

    buckets: list[list[FileEntry]] = [[] for _ in range(BULK_UPLOAD_CONCURRENCY)]
    bucket_sizes: list[int] = [0] * BULK_UPLOAD_CONCURRENCY

    for entry in sorted_files:
        placed = False
        for i in range(len(buckets)):
            if (
                len(buckets[i]) < MAX_BUCKET_FILE_COUNT
                and bucket_sizes[i] + entry.size <= MAX_BUCKET_SIZE
            ):
                buckets[i].append(entry)
                bucket_sizes[i] += entry.size
                placed = True
                break
        if not placed:
            buckets.append([entry])
            bucket_sizes.append(entry.size)

    # Drop empty buckets.
    return [b for b in buckets if b]


def upload_assets(
    client: CloudflareClient,
    files: list[FileEntry],
    *,
    account_id: str,
    project_name: str,
) -> dict[str, str]:
    """Upload assets and return the deployment manifest.

    The manifest maps ``"/relative/path"`` to the 32-character content hash.

    Steps:

    1. Fetch an upload JWT.
    2. Check which file hashes are missing on the server.
    3. Distribute missing files into upload buckets.
    4. Upload buckets concurrently.
    5. Upsert all hashes.
    6. Return the manifest.
    """
    if not files:
        return {}

    jwt = client.get_upload_token(account_id, project_name)

    # -- check missing --------------------------------------------------------

    all_hashes = [f.hash for f in files]
    hash_to_file: dict[str, FileEntry] = {f.hash: f for f in files}

    missing_hashes: list[str] = _check_missing(
        client, jwt, all_hashes, account_id, project_name
    )
    missing_files = [hash_to_file[h] for h in missing_hashes if h in hash_to_file]

    # -- upload missing files -------------------------------------------------

    if missing_files:
        buckets = _build_buckets(missing_files)
        logger.info(
            "Uploading %d files in %d bucket(s).", len(missing_files), len(buckets)
        )

        jwt = _upload_buckets(client, buckets, jwt, account_id, project_name)

    # -- upsert hashes --------------------------------------------------------

    try:
        client.request_with_jwt(
            "POST",
            "/pages/assets/upsert-hashes",
            jwt=jwt,
            body={"hashes": all_hashes},
        )
    except APIError:
        logger.warning("Failed to upsert hashes; deployment may still succeed.")

    # -- build manifest -------------------------------------------------------

    manifest: dict[str, str] = {}
    for entry in files:
        key = "/" + entry.relative_path.replace("\\", "/")
        manifest[key] = entry.hash

    return manifest


def _check_missing(
    client: CloudflareClient,
    jwt: str,
    hashes: list[str],
    account_id: str,
    project_name: str,
) -> list[str]:
    """POST to ``/pages/assets/check-missing`` with retries."""
    for attempt in range(MAX_CHECK_MISSING_ATTEMPTS):
        try:
            if is_jwt_expired(jwt):
                jwt = client.get_upload_token(account_id, project_name)
            result = client.request_with_jwt(
                "POST",
                "/pages/assets/check-missing",
                jwt=jwt,
                body={"hashes": hashes},
            )
            missing: list[str] = result  # type: ignore[assignment]
            return missing
        except APIError as exc:
            if exc.status == 401:
                jwt = client.get_upload_token(account_id, project_name)
                continue
            if attempt == MAX_CHECK_MISSING_ATTEMPTS - 1:
                raise UploadError("Failed to check missing assets.") from exc
            time.sleep(2**attempt)

    raise UploadError("Exhausted retries checking missing assets.")  # pragma: no cover


def _upload_buckets(
    client: CloudflareClient,
    buckets: list[list[FileEntry]],
    jwt: str,
    account_id: str,
    project_name: str,
) -> str:
    """Upload all buckets concurrently. Returns the (possibly refreshed) JWT."""
    with ThreadPoolExecutor(max_workers=BULK_UPLOAD_CONCURRENCY) as pool:
        futures = {
            pool.submit(
                _upload_single_bucket, client, bucket, jwt, account_id, project_name
            ): i
            for i, bucket in enumerate(buckets)
        }
        for future in as_completed(futures):
            jwt = future.result()

    return jwt


def _upload_single_bucket(
    client: CloudflareClient,
    bucket: list[FileEntry],
    jwt: str,
    account_id: str,
    project_name: str,
) -> str:
    """Upload a single bucket with retries. Returns the (possibly refreshed) JWT."""
    payload = [
        {
            "key": entry.hash,
            "value": base64.b64encode(entry.absolute_path.read_bytes()).decode("ascii"),
            "metadata": {"contentType": entry.content_type},
            "base64": True,
        }
        for entry in bucket
    ]

    for attempt in range(MAX_UPLOAD_ATTEMPTS):
        try:
            if is_jwt_expired(jwt):
                jwt = client.get_upload_token(account_id, project_name)

            client.request_with_jwt(
                "POST",
                "/pages/assets/upload",
                jwt=jwt,
                body=payload,
            )
            return jwt
        except APIError as exc:
            if exc.status == 401:
                jwt = client.get_upload_token(account_id, project_name)
                continue
            if attempt == MAX_UPLOAD_ATTEMPTS - 1:
                raise UploadError(
                    f"Failed to upload bucket after {MAX_UPLOAD_ATTEMPTS} attempts."
                ) from exc
            backoff = 2**attempt
            logger.warning(
                "Upload attempt %d failed, retrying in %ds: %s",
                attempt + 1,
                backoff,
                exc,
            )
            time.sleep(backoff)

    raise UploadError("Exhausted upload retries.")  # pragma: no cover
