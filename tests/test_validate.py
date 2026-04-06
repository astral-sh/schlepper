"""Tests for schlepper._validate."""

from __future__ import annotations

from pathlib import Path

import pytest

from schlepper._errors import ValidationError
from schlepper._validate import validate_directory


class TestValidateDirectory:
    def test_basic(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<h1>hi</h1>")
        (tmp_path / "style.css").write_text("body {}")
        entries = validate_directory(tmp_path)
        assert len(entries) == 2
        paths = {e.relative_path for e in entries}
        assert paths == {"index.html", "style.css"}

    def test_nested(self, tmp_path: Path) -> None:
        sub = tmp_path / "assets" / "js"
        sub.mkdir(parents=True)
        (sub / "app.js").write_text("// code")
        entries = validate_directory(tmp_path)
        assert len(entries) == 1
        assert entries[0].relative_path == "assets/js/app.js"

    def test_not_a_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="Not a directory"):
            validate_directory(tmp_path / "nonexistent")

    def test_file_too_large(self, tmp_path: Path) -> None:
        big = tmp_path / "big.bin"
        # Write just over 25 MiB.
        big.write_bytes(b"\x00" * (25 * 1024 * 1024 + 1))
        with pytest.raises(ValidationError, match="25 MiB"):
            validate_directory(tmp_path)

    def test_too_many_files(self, tmp_path: Path) -> None:
        for i in range(11):
            (tmp_path / f"f{i}.txt").write_text(str(i))
        with pytest.raises(ValidationError, match="Too many files"):
            validate_directory(tmp_path, max_file_count=10)

    def test_ignores_top_level_special(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<h1>hi</h1>")
        (tmp_path / "_headers").write_text("/*\n  X-Frame: DENY")
        (tmp_path / "_redirects").write_text("/old /new 301")
        (tmp_path / "_routes.json").write_text("{}")
        (tmp_path / "_worker.js").write_text("export default {}")
        entries = validate_directory(tmp_path)
        assert len(entries) == 1
        assert entries[0].relative_path == "index.html"

    def test_ignores_dot_files(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<h1>hi</h1>")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        (tmp_path / ".DS_Store").write_bytes(b"\x00")
        entries = validate_directory(tmp_path)
        assert len(entries) == 1

    def test_ignores_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<h1>hi</h1>")
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        entries = validate_directory(tmp_path)
        assert len(entries) == 1

    def test_content_type(self, tmp_path: Path) -> None:
        (tmp_path / "page.html").write_text("<html>")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "unknown.xyz123").write_bytes(b"\x00")
        entries = validate_directory(tmp_path)
        types = {e.relative_path: e.content_type for e in entries}
        assert types["page.html"] == "text/html"
        assert types["data.json"] == "application/json"
        assert types["unknown.xyz123"] == "application/octet-stream"

    def test_hash_populated(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        entries = validate_directory(tmp_path)
        assert len(entries[0].hash) == 32

    def test_empty_directory(self, tmp_path: Path) -> None:
        entries = validate_directory(tmp_path)
        assert entries == []
