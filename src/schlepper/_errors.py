"""Exception hierarchy for schlepper."""

from __future__ import annotations


class SchlepperError(Exception):
    """Base exception for all schlepper errors."""


class AuthenticationError(SchlepperError):
    """Raised when authentication fails or credentials are missing."""


class APIError(SchlepperError):
    """Raised when the Cloudflare API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: int | None = None,
        errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.errors = errors or []


class ValidationError(SchlepperError):
    """Raised when directory validation fails."""


class UploadError(SchlepperError):
    """Raised when asset upload fails after exhausting retries."""


class DeploymentError(SchlepperError):
    """Raised when deployment creation or status polling fails."""
