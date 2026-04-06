"""Tests for schlepper._upload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from schlepper._client import CloudflareClient
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
