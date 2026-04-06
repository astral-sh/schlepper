"""Tests for schlepper._upload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from schlepper._client import CloudflareClient
from schlepper._errors import UploadError
from schlepper._types import ApiToken, FileEntry
from schlepper._upload import _build_buckets, upload_assets
from tests.conftest import make_cf_response, make_fake_jwt


def _make_entry(
    tmp_path: Path, name: str, content: bytes, *, hash_val: str | None = None
) -> FileEntry:
    """Create a file and return a FileEntry for it."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return FileEntry(
        relative_path=name,
        absolute_path=p,
        content_type="application/octet-stream",
        size=len(content),
        hash=hash_val or f"{name:_<32}"[:32],
    )


class TestBuildBuckets:
    def test_single_file(self, tmp_path: Path) -> None:
        entry = _make_entry(tmp_path, "a.txt", b"hello")
        buckets = _build_buckets([entry])
        assert len(buckets) == 1
        assert buckets[0] == [entry]

    def test_distributes_across_buckets(self, tmp_path: Path) -> None:
        entries = [
            _make_entry(tmp_path, f"f{i}.txt", b"x" * 100, hash_val=f"hash{i:028d}")
            for i in range(6)
        ]
        buckets = _build_buckets(entries)
        # With 6 small files and 3 initial buckets, they should spread out.
        assert len(buckets) <= 3
        total = sum(len(b) for b in buckets)
        assert total == 6

    def test_respects_size_limit(self, tmp_path: Path) -> None:
        # Create files close to the bucket size limit.
        big = _make_entry(
            tmp_path, "big.bin", b"x" * (35 * 1024 * 1024), hash_val="a" * 32
        )
        medium = _make_entry(
            tmp_path, "med.bin", b"y" * (10 * 1024 * 1024), hash_val="b" * 32
        )
        buckets = _build_buckets([big, medium])
        # They shouldn't be in the same bucket (total > 40 MiB).
        assert len(buckets) == 2

    def test_empty_input(self) -> None:
        assert _build_buckets([]) == []


class TestUploadAssets:
    def test_full_flow(self, tmp_path: Path) -> None:
        """Test the complete upload flow with mocked HTTP."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "index.html", b"<h1>hi</h1>", hash_val="a" * 32)

        # Mock responses in order:
        # 1. get_upload_token
        # 2. check-missing (returns all hashes as missing)
        # 3. upload bucket
        # 4. upsert-hashes
        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),  # upload token
            make_cf_response(["a" * 32]),  # check-missing
            make_cf_response(None),  # upload
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/index.html": "a" * 32}

    def test_no_files(self) -> None:
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)
        manifest = upload_assets(client, [], account_id="acct", project_name="proj")
        assert manifest == {}

    def test_nothing_missing(self, tmp_path: Path) -> None:
        """When all files already exist, no upload should happen."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hello", hash_val="b" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),  # upload token
            make_cf_response([]),  # check-missing: nothing missing
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "b" * 32}

    def test_upsert_hashes_failure_is_warning(self, tmp_path: Path) -> None:
        """upsert-hashes failure should not raise."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hello", hash_val="c" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),  # nothing missing
            make_cf_response(  # upsert-hashes fails
                success=False, status=500, errors=[{"message": "internal"}]
            ),
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "c" * 32}

    @patch("schlepper._upload.time.sleep")
    def test_check_missing_retries_on_401(
        self, mock_sleep: object, tmp_path: Path
    ) -> None:
        """check-missing should refresh JWT on 401."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="d" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),  # initial token
            make_cf_response(  # check-missing 401
                success=False, status=401, errors=[{"message": "unauthorized"}]
            ),
            make_cf_response({"jwt": make_fake_jwt()}),  # refresh token
            make_cf_response([]),  # check-missing succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "d" * 32}

    @patch("schlepper._upload.time.sleep")
    def test_check_missing_retries_on_server_error(
        self, mock_sleep: object, tmp_path: Path
    ) -> None:
        """check-missing should retry on non-401 errors."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="e" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response(  # check-missing 500
                success=False, status=500, errors=[{"message": "server error"}]
            ),
            make_cf_response([]),  # check-missing retry succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "e" * 32}

    @patch("schlepper._upload.time.sleep")
    def test_check_missing_exhausted(self, mock_sleep: object, tmp_path: Path) -> None:
        """check-missing raises UploadError after exhausting retries."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="f" * 32)

        error_resp = make_cf_response(
            success=False, status=500, errors=[{"message": "fail"}]
        )

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            *([error_resp] * 5),
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            with pytest.raises(UploadError, match="check missing"):
                upload_assets(client, [entry], account_id="acct", project_name="proj")

    @patch("schlepper._upload.time.sleep")
    def test_upload_retries_on_401(self, mock_sleep: object, tmp_path: Path) -> None:
        """Upload should refresh JWT on 401 and retry."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="g" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),  # initial token
            make_cf_response(["g" * 32]),  # check-missing
            make_cf_response(  # upload 401
                success=False, status=401, errors=[{"message": "unauthorized"}]
            ),
            make_cf_response({"jwt": make_fake_jwt()}),  # refresh token
            make_cf_response(None),  # upload retry succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "g" * 32}

    @patch("schlepper._upload.time.sleep")
    def test_upload_retries_on_server_error(
        self, mock_sleep: object, tmp_path: Path
    ) -> None:
        """Upload should retry on non-401 errors with backoff."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="h" * 32)

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response(["h" * 32]),  # check-missing
            make_cf_response(  # upload 500
                success=False, status=500, errors=[{"message": "error"}]
            ),
            make_cf_response(None),  # upload retry succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "h" * 32}

    @patch("schlepper._upload.time.sleep")
    def test_upload_exhausted(self, mock_sleep: object, tmp_path: Path) -> None:
        """Upload raises UploadError after exhausting retries."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="i" * 32)

        error_resp = make_cf_response(
            success=False, status=500, errors=[{"message": "fail"}]
        )

        responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response(["i" * 32]),  # check-missing
            *([error_resp] * 5),  # all upload attempts fail
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            with pytest.raises(UploadError, match="upload bucket"):
                upload_assets(client, [entry], account_id="acct", project_name="proj")

    def test_check_missing_refreshes_expired_jwt(self, tmp_path: Path) -> None:
        """check-missing should refresh an expired JWT before calling the API."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="j" * 32)

        expired_jwt = make_fake_jwt(exp=0)  # already expired
        fresh_jwt = make_fake_jwt()

        responses = [
            make_cf_response({"jwt": expired_jwt}),  # initial (expired) token
            make_cf_response({"jwt": fresh_jwt}),  # refresh triggered by expiry check
            make_cf_response([]),  # check-missing succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            manifest = upload_assets(
                client, [entry], account_id="acct", project_name="proj"
            )

        assert manifest == {"/a.txt": "j" * 32}

    def test_upload_refreshes_expired_jwt(self, tmp_path: Path) -> None:
        """Upload should refresh an expired JWT before uploading."""
        creds = ApiToken(token="tok")
        client = CloudflareClient(creds)

        entry = _make_entry(tmp_path, "a.txt", b"hi", hash_val="k" * 32)

        expired_jwt = make_fake_jwt(exp=0)

        responses = [
            make_cf_response({"jwt": expired_jwt}),  # initial (expired) token
            # check-missing: jwt is expired, so refresh first
            make_cf_response({"jwt": make_fake_jwt()}),  # refresh for check-missing
            make_cf_response(["k" * 32]),  # check-missing
            # upload: the jwt from check-missing is fresh, but let's make it
            # expired again via mock to test the upload refresh path
            make_cf_response(None),  # upload succeeds
            make_cf_response(None),  # upsert-hashes
        ]

        with patch.object(client._pool, "request", side_effect=responses):
            # Patch is_jwt_expired to return True only on the upload call
            original_expired = __import__(
                "schlepper._upload", fromlist=["is_jwt_expired"]
            ).is_jwt_expired
            call_count = {"n": 0}

            def mock_expired(token: str) -> bool:
                call_count["n"] += 1
                # First call is check-missing (already tested above),
                # second is upload — force refresh there
                if call_count["n"] == 2:
                    return True
                return original_expired(token)

            with patch("schlepper._upload.is_jwt_expired", side_effect=mock_expired):
                # Need extra response for the upload JWT refresh
                responses_with_refresh = [
                    make_cf_response({"jwt": make_fake_jwt()}),  # initial token
                    make_cf_response(["k" * 32]),  # check-missing
                    make_cf_response({"jwt": make_fake_jwt()}),  # refresh for upload
                    make_cf_response(None),  # upload
                    make_cf_response(None),  # upsert-hashes
                ]
                with patch.object(
                    client._pool, "request", side_effect=responses_with_refresh
                ):
                    manifest = upload_assets(
                        client, [entry], account_id="acct", project_name="proj"
                    )

        assert manifest == {"/a.txt": "k" * 32}

    def test_bucket_overflow(self, tmp_path: Path) -> None:
        """Files that don't fit in initial buckets create new ones."""
        from schlepper._constants import MAX_BUCKET_FILE_COUNT

        entries = [
            _make_entry(tmp_path, f"f{i}.txt", b"x", hash_val=f"{i:032d}")
            for i in range(MAX_BUCKET_FILE_COUNT * 3 + 1)
        ]
        buckets = _build_buckets(entries)
        total = sum(len(b) for b in buckets)
        assert total == MAX_BUCKET_FILE_COUNT * 3 + 1
        # Must have created at least one extra bucket beyond the initial 3.
        assert len(buckets) >= 4
