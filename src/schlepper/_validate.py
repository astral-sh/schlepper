"""Directory walking and file validation."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from schlepper._constants import MAX_ASSET_COUNT, MAX_ASSET_SIZE
from schlepper._errors import ValidationError
from schlepper._hash import hash_file
from schlepper._types import FileEntry

# Patterns ignored at any directory level.
_ALWAYS_IGNORED: frozenset[str] = frozenset(
    {
        ".DS_Store",
        "node_modules",
        ".git",
    }
)

# Names ignored only at the top level of the deploy directory.
_TOP_LEVEL_IGNORED: frozenset[str] = frozenset(
    {
        "_worker.js",
        "_headers",
        "_redirects",
        "_routes.json",
        "functions",
        ".wrangler",
    }
)


def validate_directory(
    directory: Path,
    *,
    max_file_count: int = MAX_ASSET_COUNT,
) -> list[FileEntry]:
    """Walk *directory* and return validated :class:`FileEntry` objects.

    Raises :class:`~schlepper.ValidationError` if:

    * *directory* does not exist or is not a directory.
    * Any single file exceeds 25 MiB.
    * The total number of files exceeds *max_file_count*.
    """
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValidationError(f"Not a directory: {directory}")

    entries: list[FileEntry] = []

    for path in sorted(directory.rglob("*")):
        # NOTE: wrangler follows symlinks (its stat + isSymbolicLink check
        # is effectively dead code). We intentionally skip them to avoid
        # accidentally uploading files outside the deploy directory.
        if not path.is_file() or path.is_symlink():
            continue

        # Check ignore rules.
        relative = path.relative_to(directory)
        parts = relative.parts

        if any(part in _ALWAYS_IGNORED for part in parts):
            continue

        if parts[0] in _TOP_LEVEL_IGNORED:
            continue

        size = path.stat().st_size
        if size > MAX_ASSET_SIZE:
            raise ValidationError(
                f"File exceeds 25 MiB limit ({size} bytes): {relative}"
            )

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        file_hash = hash_file(path)

        entries.append(
            FileEntry(
                relative_path=str(relative),
                absolute_path=path,
                content_type=content_type,
                size=size,
                hash=file_hash,
            )
        )

    if len(entries) > max_file_count:
        raise ValidationError(f"Too many files: {len(entries)} (max {max_file_count})")

    return entries
