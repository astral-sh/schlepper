"""Shared test fixtures."""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
import urllib3

from schlepper._types import ApiToken


@pytest.fixture
def credentials() -> ApiToken:
    """Return test API-token credentials."""
    return ApiToken(token="test-api-token")


def make_cf_response(
    result: Any = None,
    *,
    success: bool = True,
    status: int = 200,
    errors: list[dict[str, Any]] | None = None,
) -> urllib3.HTTPResponse:
    """Build a mock :class:`urllib3.HTTPResponse` with a Cloudflare envelope."""
    body = {
        "success": success,
        "result": result,
        "errors": errors or [],
        "messages": [],
    }
    resp = MagicMock(spec=urllib3.HTTPResponse)
    resp.status = status
    resp.data = json.dumps(body).encode()
    return resp


def make_fake_jwt(**extra_claims: Any) -> str:
    """Build a fake JWT with a far-future expiry."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode()
    payload = {"exp": int(time.time()) + 3600, **extra_claims}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{header}.{body}.fakesig"
