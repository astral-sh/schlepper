"""Tests for schlepper._auth."""

from __future__ import annotations

import base64
import json
import time

import pytest

from schlepper._auth import is_jwt_expired, max_file_count_from_jwt
from schlepper._errors import AuthenticationError


def _make_jwt(payload: dict[str, object]) -> str:
    """Build a fake JWT with the given payload (no signature verification)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{header}.{body}.sig"


class TestJWT:
    def test_expired(self) -> None:
        token = _make_jwt({"exp": int(time.time()) - 100})
        assert is_jwt_expired(token) is True

    def test_not_expired(self) -> None:
        token = _make_jwt({"exp": int(time.time()) + 3600})
        assert is_jwt_expired(token) is False

    def test_no_exp_claim(self) -> None:
        token = _make_jwt({})
        assert is_jwt_expired(token) is False

    def test_max_file_count(self) -> None:
        token = _make_jwt({"max_file_count_allowed": 5000})
        assert max_file_count_from_jwt(token) == 5000

    def test_max_file_count_default(self) -> None:
        token = _make_jwt({})
        assert max_file_count_from_jwt(token) == 20_000

    def test_invalid_jwt_raises(self) -> None:
        with pytest.raises(AuthenticationError):
            is_jwt_expired("not-a-jwt")
