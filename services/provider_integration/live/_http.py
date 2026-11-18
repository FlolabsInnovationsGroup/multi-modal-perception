"""Locked-down HTTP calls to the FloBrain backend (T5).

Every call goes only to the configured HTTPS origin and to one of the agreed
paths, with no redirects, no proxy or environment settings, identity encoding,
a byte cap enforced while receiving, and the service secret as a Bearer header.
Response bodies are never logged. Failures raise ``BackendCallError`` with a
short kind and no payload.
"""

from __future__ import annotations

import json
from typing import FrozenSet, Optional, Tuple

import httpx

from services.provider_integration.live.config import LiveSettings

KIND_BLOCKED = "blocked"
KIND_UNAVAILABLE = "unavailable"
KIND_INVALID = "invalid"


class BackendCallError(Exception):
    """A backend call failed. Carries only a short kind, never a payload."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class PinnedTransport(httpx.AsyncBaseTransport):
    """Allows only the configured origin and paths; caps response size while reading."""

    def __init__(self, inner: httpx.AsyncBaseTransport, settings: LiveSettings, paths: FrozenSet[str]) -> None:
        origin = httpx.URL(settings.backend_base_url)
        self._inner = inner
        self._host = origin.host
        self._port = origin.port or 443
        self._paths = paths
        self._limit = settings.max_backend_response_bytes

    def _approved(self, url: httpx.URL) -> bool:
        return (
            url.scheme == "https"
            and url.host == self._host
            and (url.port or 443) == self._port
            and url.path in self._paths
            and not url.userinfo
            and not url.query
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._approved(request.url):
            raise BackendCallError(KIND_BLOCKED)
        request.headers["Accept-Encoding"] = "identity"
        response = await self._inner.handle_async_request(request)
        declared = response.headers.get("content-length")
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        try:
            too_long = declared is not None and int(declared) > self._limit
        except ValueError:
            too_long = True
        if too_long or encoding not in ("", "identity"):
            await response.aclose()
            raise BackendCallError(KIND_INVALID)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=response.stream,
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


async def call_backend(
    settings: LiveSettings,
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    timeout_seconds: float,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Tuple[int, object]:
    """Make one bounded call and return ``(status, parsed JSON or None)``."""
    # trust_env=False on the transport too (review fix 4): SSL_CERT_FILE / SSL_CERT_DIR and proxy
    # variables from the environment must not change which certificates are trusted.
    inner = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0, verify=True, trust_env=False)
    pinned = PinnedTransport(inner, settings, frozenset({settings.jwks_path, settings.resolve_path}))
    headers = {"Authorization": "Bearer " + settings.service_secret.reveal_for_session(), "Accept": "application/json"}
    timeout = httpx.Timeout(timeout_seconds)
    failure: Optional[str] = None
    status = 0
    body = bytearray()
    try:
        async with httpx.AsyncClient(
            transport=pinned, timeout=timeout, follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(method, settings.url(path), headers=headers, json=json_body) as response:
                async for chunk in response.aiter_raw():
                    body.extend(chunk)
                    if len(body) > settings.max_backend_response_bytes:
                        raise BackendCallError(KIND_INVALID)
                status = response.status_code
    except BackendCallError as error:
        failure = error.kind
    except Exception:  # network failure, timeout, TLS error: no detail retained
        failure = KIND_UNAVAILABLE
    finally:
        headers.clear()
    if failure is not None:
        # Raised outside the except block so no httpx exception (whose request carries the
        # service secret) stays reachable through __context__.
        raise BackendCallError(failure)
    if status != 200:
        return status, None
    try:
        return status, json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        failure = KIND_INVALID
    raise BackendCallError(failure)
