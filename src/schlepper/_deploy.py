"""High-level deployment orchestration."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from schlepper._client import CloudflareClient
from schlepper._constants import (
    MAX_COMMIT_MESSAGE_BYTES,
    MAX_DEPLOYMENT_ATTEMPTS,
    MAX_DEPLOYMENT_STATUS_ATTEMPTS,
)
from schlepper._errors import APIError, DeploymentError
from schlepper._types import Credentials, Deployment
from schlepper._upload import upload_assets
from schlepper._validate import validate_directory

logger = logging.getLogger("schlepper")

# Special files sent as form fields alongside the manifest.
_SPECIAL_FILES: dict[str, str] = {
    "_headers": "text/plain",
    "_redirects": "text/plain",
    "_routes.json": "application/json",
}


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate *text* so its UTF-8 encoding is at most *max_bytes*."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Truncate at a valid character boundary.
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def deploy(
    directory: str | Path,
    *,
    project_name: str,
    account_id: str,
    credentials: Credentials,
    branch: str | None = None,
    commit_hash: str | None = None,
    commit_message: str | None = None,
    commit_dirty: bool | None = None,
) -> Deployment:
    """Deploy a directory of static assets to Cloudflare Pages.

    This is the primary entry point for the library.  At minimum you need
    to supply the *directory* to deploy, a *project_name*, an
    *account_id*, and *credentials*.

    Returns a :class:`~schlepper.Deployment` describing the result once the
    deployment reaches a terminal state.
    """
    directory = Path(directory).resolve()
    client = CloudflareClient(credentials)

    # 1. Validate directory.
    files = validate_directory(directory)
    logger.info("Validated %d files in %s.", len(files), directory)

    # 2. Upload assets.
    manifest = upload_assets(
        client,
        files,
        account_id=account_id,
        project_name=project_name,
    )
    logger.info("Upload complete. Manifest has %d entries.", len(manifest))

    # 3. Build multipart form for deployment creation.
    fields: dict[str, object] = {
        "manifest": json.dumps(manifest),
    }

    if branch is not None:
        fields["branch"] = branch
    if commit_hash is not None:
        fields["commit_hash"] = commit_hash
    if commit_message is not None:
        fields["commit_message"] = _truncate_utf8(
            commit_message, MAX_COMMIT_MESSAGE_BYTES
        )
    if commit_dirty is not None:
        fields["commit_dirty"] = str(commit_dirty).lower()

    # Attach special files if present in the deploy directory.
    for filename, content_type in _SPECIAL_FILES.items():
        path = directory / filename
        if path.is_file():
            fields[filename] = (filename, path.read_bytes(), content_type)

    # 4. Create deployment with retries.
    deploy_path = f"/accounts/{account_id}/pages/projects/{project_name}/deployments"
    result = _create_deployment(client, deploy_path, fields)

    deployment_id: str = result["id"]
    url: str = result.get("url", "")
    environment: str = result.get("environment", "production")

    logger.info("Deployment %s created (%s).", deployment_id, environment)

    # 5. Poll for terminal status.
    status, aliases = _poll_deployment(client, deploy_path + f"/{deployment_id}")

    return Deployment(
        id=deployment_id,
        url=url,
        environment=environment,
        project_name=project_name,
        aliases=aliases,
        status=status,
    )


def _create_deployment(
    client: CloudflareClient,
    path: str,
    fields: dict[str, object],
) -> dict[str, Any]:
    """POST the deployment with retries."""
    last_exc: Exception | None = None
    for attempt in range(MAX_DEPLOYMENT_ATTEMPTS):
        try:
            result: dict[str, Any] = client.upload_multipart(path, fields)
            return result
        except APIError as exc:
            last_exc = exc
            if exc.code == 8000000 and attempt < MAX_DEPLOYMENT_ATTEMPTS - 1:
                backoff = 2**attempt
                logger.warning(
                    "Deployment attempt %d failed (code %s), retrying in %ds.",
                    attempt + 1,
                    exc.code,
                    backoff,
                )
                time.sleep(backoff)
                continue
            raise DeploymentError(str(exc)) from exc

    raise DeploymentError(
        "Exhausted deployment retries."
    ) from last_exc  # pragma: no cover


def _poll_deployment(client: CloudflareClient, path: str) -> tuple[str, list[str]]:
    """Poll deployment status until it reaches a terminal state.

    Returns ``(status, aliases)`` where *status* is ``"success"`` or
    ``"failure"``.
    """
    for attempt in range(MAX_DEPLOYMENT_STATUS_ATTEMPTS):
        try:
            result = client.request("GET", path)
            stage = result.get("latest_stage", {})
            status = stage.get("status", "")
            if status in ("success", "failure"):
                aliases: list[str] = result.get("aliases", []) or []
                if status == "failure":
                    logger.error("Deployment failed at stage %r.", stage.get("name"))
                return status, aliases
        except APIError:
            pass

        backoff = 2**attempt
        time.sleep(backoff)

    logger.warning("Timed out polling deployment status.")
    return "unknown", []
