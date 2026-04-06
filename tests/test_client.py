"""Tests for schlepper._client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from schlepper._client import CloudflareClient
from schlepper._errors import APIError
from schlepper._types import ApiKey, Credentials
from tests.conftest import make_cf_response


class TestCloudflareClient:
    def test_request_success(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response({"name": "my-project"})

        with patch.object(client._pool, "request", return_value=mock_resp) as m:
            result = client.request("GET", "/accounts/abc/pages/projects/proj")

        assert result == {"name": "my-project"}
        _, kwargs = m.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-api-token"

    def test_request_api_error(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response(
            success=False,
            status=404,
            errors=[{"code": 8000007, "message": "Project not found"}],
        )

        with patch.object(client._pool, "request", return_value=mock_resp):
            with pytest.raises(APIError, match="Project not found") as exc_info:
                client.request("GET", "/accounts/abc/pages/projects/nope")

        assert exc_info.value.status == 404
        assert exc_info.value.code == 8000007

    def test_api_key_auth_headers(self) -> None:
        creds = ApiKey(key="my-key", email="a@b.com")
        client = CloudflareClient(creds)
        mock_resp = make_cf_response({"ok": True})

        with patch.object(client._pool, "request", return_value=mock_resp) as m:
            client.request("GET", "/test")

        _, kwargs = m.call_args
        assert kwargs["headers"]["X-Auth-Key"] == "my-key"
        assert kwargs["headers"]["X-Auth-Email"] == "a@b.com"

    def test_request_with_body(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response(["hash1"])

        with patch.object(client._pool, "request", return_value=mock_resp) as m:
            result = client.request(
                "POST", "/pages/assets/check-missing", body={"hashes": ["hash1"]}
            )

        assert result == ["hash1"]
        _, kwargs = m.call_args
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert json.loads(kwargs["body"]) == {"hashes": ["hash1"]}

    def test_request_with_jwt(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response(None)

        with patch.object(client._pool, "request", return_value=mock_resp) as m:
            client.request_with_jwt(
                "POST",
                "/pages/assets/upload",
                jwt="my-jwt",
                body=[],
            )

        _, kwargs = m.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer my-jwt"

    def test_get_upload_token(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response({"jwt": "upload-jwt-123"})

        with patch.object(client._pool, "request", return_value=mock_resp):
            jwt = client.get_upload_token("acct-id", "my-proj")

        assert jwt == "upload-jwt-123"

    def test_invalid_json_response(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        resp = MagicMock()
        resp.status = 500
        resp.data = b"not json"

        with patch.object(client._pool, "request", return_value=resp):
            with pytest.raises(APIError, match="Invalid JSON"):
                client.request("GET", "/test")

    def test_upload_multipart(self, credentials: Credentials) -> None:
        client = CloudflareClient(credentials)
        mock_resp = make_cf_response({"id": "deploy-123"})

        with patch.object(client._pool, "request", return_value=mock_resp) as m:
            result = client.upload_multipart(
                "/accounts/abc/pages/projects/proj/deployments",
                {"manifest": "{}"},
            )

        assert result == {"id": "deploy-123"}
        args, kwargs = m.call_args
        assert args[0] == "POST"
        assert kwargs["fields"] == {"manifest": "{}"}
