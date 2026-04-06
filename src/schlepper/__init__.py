"""Schlepper: a Python library for deploying to Cloudflare Pages."""

from schlepper._deploy import deploy
from schlepper._errors import (
    APIError,
    AuthenticationError,
    DeploymentError,
    SchlepperError,
    UploadError,
    ValidationError,
)
from schlepper._types import ApiKey, ApiToken, Credentials, Deployment

__all__ = [
    "deploy",
    "ApiKey",
    "ApiToken",
    "Credentials",
    "Deployment",
    "APIError",
    "AuthenticationError",
    "DeploymentError",
    "SchlepperError",
    "UploadError",
    "ValidationError",
]
