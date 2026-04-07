"""BLAKE3 file hashing for Cloudflare Pages."""

from __future__ import annotations

import base64
from pathlib import Path

import blake3


def hash_file(path: Path) -> str:
    """Compute the Cloudflare Pages content hash for a file.

    The algorithm matches wrangler's implementation:
    ``blake3(base64(content) + extension).hex()[:32]``
    where *extension* is the file extension without the leading dot.
    """
    content = path.read_bytes()
    b64_content = base64.b64encode(content).decode("ascii")
    extension = path.suffix[1:] if path.suffix else ""
    digest = blake3.blake3((b64_content + extension).encode()).hexdigest()
    return digest[:32]
