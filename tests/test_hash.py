"""Tests for schlepper._hash."""

from __future__ import annotations

import base64
from pathlib import Path

import blake3 as blake3_mod

from schlepper._hash import hash_file


class TestHashFile:
    def test_basic_hash(self, tmp_path: Path) -> None:
        """Verify hash_file matches the wrangler algorithm manually."""
        content = b"hello world"
        p = tmp_path / "test.txt"
        p.write_bytes(content)

        # Manual computation matching wrangler:
        # blake3(base64(content) + extension).hex()[:32]
        b64 = base64.b64encode(content).decode("ascii")
        expected = blake3_mod.blake3((b64 + "txt").encode()).hexdigest()[:32]

        assert hash_file(p) == expected

    def test_no_extension(self, tmp_path: Path) -> None:
        """Files without an extension should hash with empty extension string."""
        content = b"data"
        p = tmp_path / "Makefile"
        p.write_bytes(content)

        b64 = base64.b64encode(content).decode("ascii")
        expected = blake3_mod.blake3((b64 + "").encode()).hexdigest()[:32]

        assert hash_file(p) == expected

    def test_hash_length(self, tmp_path: Path) -> None:
        p = tmp_path / "a.js"
        p.write_bytes(b"console.log('hi')")
        assert len(hash_file(p)) == 32

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        assert hash_file(a) != hash_file(b)

    def test_same_content_different_extension(self, tmp_path: Path) -> None:
        """Extension is part of the hash input, so same content with different
        extensions should produce different hashes."""
        a = tmp_path / "file.txt"
        b = tmp_path / "file.js"
        a.write_bytes(b"same")
        b.write_bytes(b"same")
        assert hash_file(a) != hash_file(b)
