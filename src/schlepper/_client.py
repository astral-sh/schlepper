"""HTTP client for the Cloudflare API."""

from __future__ import annotations

import json
from typing import Any

import urllib3

from schlepper._constants import CF_API_BASE_URL
from schlepper._errors import APIError
from schlepper._types import ApiKey, ApiToken, Credentials


class CloudflareClient:
    """Low-level HTTP client that wraps :mod:`urllib3` and handles the
    Cloudflare API response envelope.
    """

    def __init__(self, credentials: Credentials) -> None:
        self._credentials = credentials
        self._pool = urllib3.PoolManager()

    # -- public helpers -------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | list[Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> Any:
        """Make an API-token-authenticated request and return the unwrapped ``result``.

        *path* is relative to the Cloudflare API base URL
        (e.g. ``"/accounts/…/pages/projects"``).
        """
        url = CF_API_BASE_URL + path
        headers = self._auth_headers()
        encoded_body: bytes | None = None
        if body is not None:
            encoded_body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        resp = self._pool.request(
            method,
            url,
            body=encoded_body,
            headers=headers,
            fields=query if method == "GET" and query else None,
        )
        return self._unwrap(resp)

    def request_with_jwt(
        self,
        method: str,
        path: str,
        *,
        jwt: str,
        body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        """Make a JWT-authenticated request (for asset operations)."""
        url = CF_API_BASE_URL + path
        headers: dict[str, str] = {
            "Authorization": f"Bearer {jwt}",
        }
        encoded_body: bytes | None = None
        if body is not None:
            encoded_body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        resp = self._pool.request(method, url, body=encoded_body, headers=headers)
        return self._unwrap(resp)

    def upload_multipart(
        self,
        path: str,
        fields: dict[str, Any],
    ) -> Any:
        """POST multipart form data with API-token authentication.

        *fields* values may be strings or ``(filename, data, content_type)``
        tuples for file uploads.
        """
        url = CF_API_BASE_URL + path
        headers = self._auth_headers()
        resp = self._pool.request(
            "POST",
            url,
            fields=fields,
            headers=headers,
        )
        return self._unwrap(resp)

    def get_upload_token(self, account_id: str, project_name: str) -> str:
        """Fetch an upload JWT for the given project."""
        result = self.request(
            "GET",
            f"/accounts/{account_id}/pages/projects/{project_name}/upload-token",
        )
        jwt: str = result["jwt"]
        return jwt

    # -- internals ------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        match self._credentials:
            case ApiToken(token=token):
                return {"Authorization": f"Bearer {token}"}
            case ApiKey(key=key, email=email):
                return {
                    "X-Auth-Key": key,
                    "X-Auth-Email": email,
                }
            case _:
                raise AssertionError("unreachable")

    @staticmethod
    def _unwrap(resp: urllib3.BaseHTTPResponse) -> Any:
        """Parse the Cloudflare API envelope and return ``result``.

        Raises :class:`APIError` on non-success responses.
        """
        try:
            data: dict[str, Any] = json.loads(resp.data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise APIError(
                f"Invalid JSON response (HTTP {resp.status})",
                status=resp.status,
            ) from exc

        if data.get("success"):
            return data.get("result")

        errors: list[dict[str, Any]] = data.get("errors", [])
        code: int | None = errors[0].get("code") if errors else None
        messages = (
            "; ".join(e.get("message", "") for e in errors) or f"HTTP {resp.status}"
        )
        raise APIError(messages, status=resp.status, code=code, errors=errors)
