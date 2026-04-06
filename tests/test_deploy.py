"""Tests for schlepper._deploy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from schlepper._client import CloudflareClient
from schlepper._deploy import _truncate_utf8, deploy
from schlepper._errors import DeploymentError
from schlepper._types import ApiToken
from tests.conftest import make_cf_response, make_fake_jwt


class TestTruncateUtf8:
    def test_short_string(self) -> None:
        assert _truncate_utf8("hello", 384) == "hello"

    def test_truncates(self) -> None:
        result = _truncate_utf8("a" * 500, 384)
        assert len(result.encode("utf-8")) <= 384

    def test_multibyte(self) -> None:
        # Each emoji is 4 bytes in UTF-8.
        text = "\U0001f600" * 100  # 400 bytes
        result = _truncate_utf8(text, 384)
        assert len(result.encode("utf-8")) <= 384
        # Should be exactly 96 emoji (96 * 4 = 384).
        assert len(result) == 96


class TestDeploy:
    def _make_client(self, creds: ApiToken) -> CloudflareClient:
        """Create a CloudflareClient with a mocked pool."""
        with patch.object(
            CloudflareClient,
            "__init__",
            lambda self, c: (
                setattr(self, "_credentials", c) or setattr(self, "_pool", None)
            ),
        ):
            return CloudflareClient(creds)

    def test_full_deploy(self, tmp_path: Path) -> None:
        """End-to-end deploy with all HTTP calls mocked."""
        (tmp_path / "index.html").write_text("<h1>deployed</h1>")
        (tmp_path / "_headers").write_text("/*\n  X-Frame-Options: DENY")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        responses = [
            # upload_assets flow:
            make_cf_response({"jwt": make_fake_jwt()}),  # upload token
            make_cf_response([]),  # check-missing: nothing new
            make_cf_response(None),  # upsert-hashes
            # deployment creation:
            make_cf_response(
                {
                    "id": "deploy-1",
                    "url": "https://proj.pages.dev",
                    "environment": "production",
                }
            ),
            # deployment status poll:
            make_cf_response(
                {
                    "latest_stage": {"name": "deploy", "status": "success"},
                    "aliases": ["https://proj.pages.dev"],
                }
            ),
        ]

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = responses
                result = deploy(
                    tmp_path,
                    project_name="proj",
                    account_id="acct",
                    credentials=creds,
                    branch="main",
                    commit_message="deploy v1",
                )

        assert result.id == "deploy-1"
        assert result.url == "https://proj.pages.dev"
        assert result.environment == "production"
        assert result.project_name == "proj"
        assert result.status == "success"
        assert result.aliases == ["https://proj.pages.dev"]

    def test_special_files_attached(self, tmp_path: Path) -> None:
        """Verify that _headers, _redirects, and _routes.json are sent as form fields."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")
        (tmp_path / "_headers").write_text("header-content")
        (tmp_path / "_redirects").write_text("redirect-content")
        (tmp_path / "_routes.json").write_text('{"routes": []}')

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),  # upload token
            make_cf_response([]),  # check-missing
            make_cf_response(None),  # upsert-hashes
        ]

        captured_fields: dict[str, object] = {}

        def fake_upload_multipart(path: str, fields: dict[str, object]) -> object:
            captured_fields.update(fields)
            return {
                "id": "deploy-2",
                "url": "https://proj.pages.dev",
                "environment": "production",
            }

        poll_response = make_cf_response(
            {
                "latest_stage": {"name": "deploy", "status": "success"},
                "aliases": [],
            }
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [*upload_responses, poll_response]
                with patch.object(client, "upload_multipart", fake_upload_multipart):
                    result = deploy(
                        tmp_path,
                        project_name="proj",
                        account_id="acct",
                        credentials=creds,
                    )

        assert result.status == "success"
        assert "_headers" in captured_fields
        assert "_redirects" in captured_fields
        assert "_routes.json" in captured_fields
        assert "manifest" in captured_fields

    def test_commit_hash_and_dirty(self, tmp_path: Path) -> None:
        """Verify commit_hash and commit_dirty are passed through."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]

        captured_fields: dict[str, object] = {}

        def fake_upload_multipart(path: str, fields: dict[str, object]) -> object:
            captured_fields.update(fields)
            return {"id": "d", "url": "", "environment": "production"}

        poll_response = make_cf_response(
            {"latest_stage": {"status": "success"}, "aliases": []}
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [*upload_responses, poll_response]
                with patch.object(client, "upload_multipart", fake_upload_multipart):
                    deploy(
                        tmp_path,
                        project_name="p",
                        account_id="a",
                        credentials=creds,
                        commit_hash="abc123",
                        commit_dirty=True,
                    )

        assert captured_fields["commit_hash"] == "abc123"
        assert captured_fields["commit_dirty"] == "true"

    @patch("schlepper._deploy.time.sleep")
    def test_deployment_retry_on_8000000(
        self, mock_sleep: object, tmp_path: Path
    ) -> None:
        """Deployment retries on error code 8000000."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]

        deploy_error = make_cf_response(
            success=False,
            status=500,
            errors=[{"code": 8000000, "message": "Unknown error"}],
        )
        deploy_success = make_cf_response(
            {"id": "d", "url": "", "environment": "production"}
        )
        poll = make_cf_response({"latest_stage": {"status": "success"}, "aliases": []})

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [
                    *upload_responses,
                    deploy_error,
                    deploy_success,
                    poll,
                ]
                result = deploy(
                    tmp_path,
                    project_name="p",
                    account_id="a",
                    credentials=creds,
                )

        assert result.status == "success"

    def test_deployment_non_retryable_error(self, tmp_path: Path) -> None:
        """Non-retryable API errors raise DeploymentError immediately."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]

        deploy_error = make_cf_response(
            success=False,
            status=400,
            errors=[{"code": 1234, "message": "Bad request"}],
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [*upload_responses, deploy_error]
                with pytest.raises(DeploymentError):
                    deploy(
                        tmp_path,
                        project_name="p",
                        account_id="a",
                        credentials=creds,
                    )

    @patch("schlepper._deploy.time.sleep")
    def test_poll_failure_status(self, mock_sleep: object, tmp_path: Path) -> None:
        """Deployment that fails at a stage returns status='failure'."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]
        deploy_ok = make_cf_response(
            {"id": "d", "url": "", "environment": "production"}
        )
        poll_fail = make_cf_response(
            {"latest_stage": {"name": "build", "status": "failure"}, "aliases": []}
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [
                    *upload_responses,
                    deploy_ok,
                    poll_fail,
                ]
                result = deploy(
                    tmp_path,
                    project_name="p",
                    account_id="a",
                    credentials=creds,
                )

        assert result.status == "failure"

    @patch("schlepper._deploy.time.sleep")
    def test_poll_timeout(self, mock_sleep: object, tmp_path: Path) -> None:
        """Polling that never reaches terminal state returns 'unknown'."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]
        deploy_ok = make_cf_response(
            {"id": "d", "url": "", "environment": "production"}
        )
        # All poll responses return "active" (non-terminal).
        poll_active = make_cf_response(
            {"latest_stage": {"name": "deploy", "status": "active"}, "aliases": []}
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [
                    *upload_responses,
                    deploy_ok,
                    *([poll_active] * 5),
                ]
                result = deploy(
                    tmp_path,
                    project_name="p",
                    account_id="a",
                    credentials=creds,
                )

        assert result.status == "unknown"

    @patch("schlepper._deploy.time.sleep")
    def test_poll_api_error_retries(self, mock_sleep: object, tmp_path: Path) -> None:
        """Polling continues when API errors occur."""
        (tmp_path / "index.html").write_text("<h1>hi</h1>")

        creds = ApiToken(token="tok")
        client = self._make_client(creds)

        upload_responses = [
            make_cf_response({"jwt": make_fake_jwt()}),
            make_cf_response([]),
            make_cf_response(None),
        ]
        deploy_ok = make_cf_response(
            {"id": "d", "url": "", "environment": "production"}
        )
        poll_error = make_cf_response(
            success=False, status=500, errors=[{"message": "server error"}]
        )
        poll_ok = make_cf_response(
            {"latest_stage": {"status": "success"}, "aliases": ["a.pages.dev"]}
        )

        with patch("schlepper._deploy.CloudflareClient", return_value=client):
            with patch.object(client, "_pool") as mock_pool:
                mock_pool.request.side_effect = [
                    *upload_responses,
                    deploy_ok,
                    poll_error,
                    poll_ok,
                ]
                result = deploy(
                    tmp_path,
                    project_name="p",
                    account_id="a",
                    credentials=creds,
                )

        assert result.status == "success"
