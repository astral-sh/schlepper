"""Integration tests that deploy to Cloudflare Pages.

These tests are skipped by default. To run them:

    uv run pytest -m integration

They require ``CLOUDFLARE_ACCOUNT_ID``, ``CLOUDFLARE_API_TOKEN``, and
``CLOUDFLARE_SITE`` in the environment (or sourced from ``it.env``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import urllib3

import schlepper

pytestmark = pytest.mark.integration

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
SITE_URL = os.environ.get("CLOUDFLARE_SITE", "").rstrip("/")
PROJECT_NAME = "schlepper-test"

skip_unless_configured = pytest.mark.skipif(
    not (ACCOUNT_ID and API_TOKEN and SITE_URL),
    reason="CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, and CLOUDFLARE_SITE must be set",
)

_http = urllib3.PoolManager()


def _fetch(
    path: str,
    *,
    retries: int = 5,
    expect: Callable[[urllib3.BaseHTTPResponse], bool] | None = None,
) -> urllib3.BaseHTTPResponse:
    """GET a path from the site URL, retrying to allow propagation.

    If *expect* is given, keep retrying until the predicate returns ``True``
    or retries are exhausted.  This is useful for waiting on CDN propagation
    of special files like ``_headers`` and ``_redirects``.
    """
    url = f"{SITE_URL}{path}"
    for attempt in range(retries):
        resp = _http.request("GET", url, redirect=False)
        if expect is not None:
            if expect(resp):
                return resp
        elif resp.status < 500 and resp.data:
            return resp
        time.sleep(2**attempt)
    return resp


def _deploy(tmp_path: Path, *, commit_message: str) -> schlepper.Deployment:
    """Deploy helper with common arguments."""
    return schlepper.deploy(
        tmp_path,
        project_name=PROJECT_NAME,
        account_id=ACCOUNT_ID,
        credentials=schlepper.ApiToken(token=API_TOKEN),
        branch="production",
        commit_message=commit_message,
    )


@skip_unless_configured
class TestIntegrationDeploy:
    def test_deploy_simple_site(self, tmp_path: Path) -> None:
        """Deploy a minimal static site and verify content is served."""
        body = "<!doctype html><html><body><h1>schlepper simple</h1></body></html>"
        (tmp_path / "index.html").write_text(body)
        (tmp_path / "style.css").write_text("body { margin: 0; }")

        result = _deploy(tmp_path, commit_message="integration test: simple site")

        assert result.id
        assert result.url
        assert result.status == "success"
        assert result.project_name == PROJECT_NAME

        resp = _fetch("/")
        assert resp.status == 200
        assert b"schlepper simple" in resp.data

        resp = _fetch("/style.css")
        assert resp.status == 200
        assert b"margin: 0" in resp.data

    def test_deploy_nested_assets(self, tmp_path: Path) -> None:
        """Deploy a site with nested directories and fetch nested paths."""
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><body>nested test</body></html>"
        )
        assets = tmp_path / "assets" / "css"
        assets.mkdir(parents=True)
        (assets / "main.css").write_text("h1 { color: red; }")

        js = tmp_path / "assets" / "js"
        js.mkdir(parents=True)
        (js / "app.js").write_text("console.log('schlepper');")

        result = _deploy(tmp_path, commit_message="integration test: nested assets")

        assert result.status == "success"

        resp = _fetch("/assets/css/main.css")
        assert resp.status == 200
        assert b"color: red" in resp.data

        resp = _fetch("/assets/js/app.js")
        assert resp.status == 200
        assert b"schlepper" in resp.data

    def test_deploy_with_special_files(self, tmp_path: Path) -> None:
        """Deploy with _headers and _redirects and verify they take effect."""
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><body>special files test</body></html>"
        )
        (tmp_path / "_headers").write_text("/*\n  X-Schlepper-Test: true\n")
        (tmp_path / "_redirects").write_text("/old /index.html 301\n")

        result = _deploy(
            tmp_path, commit_message="integration test: special files"
        )

        assert result.status == "success"

        # Custom headers may take time to propagate through the CDN.
        resp = _fetch(
            "/",
            retries=10,
            expect=lambda r: r.headers.get("X-Schlepper-Test") == "true",
        )
        assert resp.status == 200
        assert b"special files test" in resp.data
        assert resp.headers.get("X-Schlepper-Test") == "true"

        # Redirects may also need propagation time.
        resp = _fetch(
            "/old",
            retries=10,
            expect=lambda r: r.status in (301, 302),
        )
        assert resp.status == 301

    def test_deploy_overwrites_previous(self, tmp_path: Path) -> None:
        """Deploy new content and verify it replaces the old content."""
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><body>version-one</body></html>"
        )
        result = _deploy(
            tmp_path, commit_message="integration test: overwrite v1"
        )
        assert result.status == "success"

        # Overwrite with new content.
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><body>version-two</body></html>"
        )
        result = _deploy(
            tmp_path, commit_message="integration test: overwrite v2"
        )
        assert result.status == "success"

        # CDN may serve stale content briefly after a new deploy.
        resp = _fetch(
            "/",
            retries=10,
            expect=lambda r: b"version-two" in r.data,
        )
        assert resp.status == 200
        assert b"version-two" in resp.data

    def test_deploy_idempotent(self, tmp_path: Path) -> None:
        """Deploying the same content twice should succeed both times."""
        (tmp_path / "index.html").write_text(
            "<!doctype html><html><body>idempotent test</body></html>"
        )

        first = _deploy(tmp_path, commit_message="integration test: idempotent 1")
        second = _deploy(tmp_path, commit_message="integration test: idempotent 2")

        assert first.status == "success"
        assert second.status == "success"
        assert first.id != second.id

        resp = _fetch("/")
        assert resp.status == 200
        assert b"idempotent test" in resp.data
