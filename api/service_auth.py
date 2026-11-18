"""Short-term service key check for the live routes.

Stopgap until the service runs on HTTPS in a private network: every route except
``/health`` and the token-verified provider routes (``SELF_AUTHENTICATED_PATHS``) requires ``Authorization: Bearer <MULTIMODAL_API_KEY>``, the key the
FloBrain backend already sends. It is not the M2 integration and does not
replace HTTPS: over plain HTTP the key can still be observed on the network.

Rules:
- Runs as plain ASGI middleware before the route, so a rejected request's body
  (for example a large upload) is never read.
- Compares in constant time. The expected and supplied keys are never logged or
  returned.
- Fails closed: if ``MULTIMODAL_API_KEY`` is missing, shorter than
  ``MIN_KEY_LENGTH``, non-ASCII or has surrounding whitespace, protected routes
  return 503 and nothing is let through.
- The key is read from the environment on each request, so tests and a restart
  with a new secret need no code change.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Awaitable, Callable, FrozenSet, Optional

ENV_VAR = "MULTIMODAL_API_KEY"
MIN_KEY_LENGTH = 32
OPEN_PATHS: FrozenSet[str] = frozenset({"/health"})
# Credentialed routes (provider integration T5, decision T5-D4): each request carries the
# backend's signed, short-lived token in the Authorization header and is verified by those
# routes, so the shared key check must not intercept them.
SELF_AUTHENTICATED_PATHS: FrozenSet[str] = frozenset({"/invoke", "/transcribe", "/validate"})

logger = logging.getLogger(__name__)

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


def _expected_key() -> Optional[bytes]:
    value = os.environ.get(ENV_VAR)
    if not value or value != value.strip() or len(value) < MIN_KEY_LENGTH or not value.isascii():
        return None
    return value.encode("ascii")


def _supplied_key(scope: Scope) -> Optional[bytes]:
    values = [value for name, value in scope.get("headers", ()) if name.lower() == b"authorization"]
    if len(values) != 1:
        return None
    scheme, separator, token = values[0].partition(b" ")
    if not separator or scheme.lower() != b"bearer" or not token or token != token.strip():
        return None
    return token


async def _respond(send: Send, status: int, detail: str, extra_headers: tuple = ()) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii")),
               *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class ServiceKeyMiddleware:
    """Reject every non-open HTTP request that lacks the configured service key."""

    def __init__(self, app: Callable) -> None:
        self.app = app
        self._warned_unconfigured = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path")
        if scope.get("type") != "http" or path in OPEN_PATHS or path in SELF_AUTHENTICATED_PATHS:
            await self.app(scope, receive, send)
            return
        expected = _expected_key()
        if expected is None:
            if not self._warned_unconfigured:
                logger.error("Service authentication is not configured; protected routes are refused.")
                self._warned_unconfigured = True
            await _respond(send, 503, "Service authentication is not configured.")
            return
        self._warned_unconfigured = False
        supplied = _supplied_key(scope)
        if supplied is None or not hmac.compare_digest(supplied, expected):
            await _respond(send, 401, "Unauthorized", ((b"www-authenticate", b"Bearer"),))
            return
        await self.app(scope, receive, send)
