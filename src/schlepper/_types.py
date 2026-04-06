"""Data types for schlepper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ApiToken:
    """Cloudflare API token credentials."""

    token: str


@dataclass(frozen=True, slots=True)
class ApiKey:
    """Cloudflare global API key + email credentials."""

    key: str
    email: str


type Credentials = ApiToken | ApiKey


@dataclass(frozen=True, slots=True)
class FileEntry:
    """A validated file ready for upload."""

    relative_path: str
    """Path relative to the deploy directory, e.g. ``"assets/style.css"``."""

    absolute_path: Path
    """Absolute filesystem path."""

    content_type: str
    """MIME content type."""

    size: int
    """File size in bytes."""

    hash: str
    """32-character hex BLAKE3 hash used by the Cloudflare Pages API."""


@dataclass(frozen=True, slots=True)
class Deployment:
    """Result of a Cloudflare Pages deployment."""

    id: str
    """Deployment identifier."""

    url: str
    """URL where the deployment is accessible."""

    environment: str
    """``"production"`` or ``"preview"``."""

    project_name: str
    """Name of the Pages project."""

    aliases: list[str] = field(default_factory=list)
    """Alternative URLs (e.g. ``*.pages.dev`` aliases)."""

    status: str = "unknown"
    """Terminal status: ``"success"``, ``"failure"``, or ``"unknown"``."""
