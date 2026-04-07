"""JWT utilities."""

from __future__ import annotations

import base64
import json
import time

from schlepper._errors import AuthenticationError


def _decode_jwt_payload(token: str) -> dict[str, object]:
    """Decode a JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Invalid JWT format.")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data: dict[str, object] = json.loads(base64.urlsafe_b64decode(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AuthenticationError("Failed to decode JWT payload.") from exc
    return data


def is_jwt_expired(token: str) -> bool:
    """Return ``True`` if the JWT's ``exp`` claim is in the past."""
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not isinstance(exp, int | float):
        return False
    return time.time() >= exp
