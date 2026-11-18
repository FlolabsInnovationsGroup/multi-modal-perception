"""Credentialed provider routes: /invoke, /transcribe and /validate (T5.4).

Each request must carry the backend's signed token as ``Authorization: Bearer``.
The token is fully verified before the request body is read; the body is read
into memory with a size cap and never written to disk; the provider module
then re-verifies the token, fetches exactly the named key version from the
backend and runs one operation. Responses use the D-2 format.

These routes do not use the shared MULTIMODAL_API_KEY guard: they carry their
own signed token (T5-D4). The live settings come from the environment; when
any is missing the routes answer 503 NOT_CONFIGURED and never reach a key.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Mapping, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from python_multipart.multipart import FormParser, parse_options_header

from services.provider_integration.config import LOCAL_LIMIT_PROFILE, LimitProfile
from services.provider_integration.errors import ErrorCode
from services.provider_integration.handler import Handler
from services.provider_integration.http_contract import error_response, to_http, validation_to_http
from services.provider_integration.live.config import load_live_settings, openai_provider_config
from services.provider_integration.live.reader import BackendCredentialReader
from services.provider_integration.live.verifier import JwtContextVerifier
from services.provider_integration.types import BoundaryFailure, ContextKind
from services.provider_integration.wiring import build_handler

JSON_BODY_LIMIT = 512 * 1024
MULTIPART_OVERHEAD = 256 * 1024
INVOKE_FIELDS = frozenset({"text", "generation_model"})
VALIDATE_FIELDS = frozenset({"operation", "model"})
TRANSCRIBE_TEXT_FIELDS = frozenset({"audio_format", "transcription_model", "generation_model", "text"})


@dataclass(frozen=True)
class LiveRoute:
    """Everything one request needs: the handler, the token checker and the limits."""

    handler: Handler
    verifier: JwtContextVerifier
    limits: LimitProfile


class _BadRequest(Exception):
    """The request body or headers were rejected. Never carries the input."""


def build_from_environment(env: Mapping[str, str]) -> Optional[LiveRoute]:
    """Compose the live route dependencies, or ``None`` when settings are incomplete."""
    settings = load_live_settings(env)
    if settings is None:
        return None
    from services.openai_service import SYSTEM_PROMPT  # the existing fixed system prompt (L6)

    verifier = JwtContextVerifier(settings)
    handler = build_handler(
        verifier=verifier,
        reader=BackendCredentialReader(settings),
        providers={"openai": openai_provider_config(settings, SYSTEM_PROMPT)},
        limits=LOCAL_LIMIT_PROFILE,
    )
    return LiveRoute(handler=handler, verifier=verifier, limits=LOCAL_LIMIT_PROFILE)


class _LazyLive:
    """Builds the live dependencies on first use and keeps them once complete."""

    def __init__(self, factory: Callable[[], Optional[LiveRoute]]) -> None:
        self._factory = factory
        self._live: Optional[LiveRoute] = None

    def get(self) -> Optional[LiveRoute]:
        if self._live is None:
            self._live = self._factory()
        return self._live


def _respond(result: Tuple[int, Dict[str, object]]) -> JSONResponse:
    status, body = result
    return JSONResponse(status_code=status, content=body)


def _bearer(request: Request) -> Optional[str]:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        return None
    scheme, separator, token = values[0].partition(" ")
    if not separator or scheme.lower() != "bearer" or not token or token != token.strip():
        return None
    return token


async def _read_capped(request: Request, limit: int) -> bytearray:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise _BadRequest()
        except ValueError:
            raise _BadRequest() from None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise _BadRequest()
    return body


def _json_object(body: bytearray, fields: frozenset, required: frozenset) -> Dict[str, object]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # review fix 3: deep nesting is a bad request
        raise _BadRequest() from None
    if not isinstance(data, dict) or set(data) - fields or required - set(data):
        raise _BadRequest()
    return data


def _multipart_in_memory(content_type: str, body: bytearray, limit: int) -> Dict[str, object]:
    """Parse multipart form data entirely in memory: nothing is written to disk."""
    media_type, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise _BadRequest()
    fields: Dict[str, object] = {}
    files = []

    def on_field(field) -> None:
        name = field.field_name.decode("utf-8", "strict") if field.field_name else ""
        if name not in TRANSCRIBE_TEXT_FIELDS or name in fields:
            raise _BadRequest()
        fields[name] = (field.value or b"").decode("utf-8", "strict")

    def on_file(file) -> None:
        files.append(file)

    parser = FormParser(
        "multipart/form-data", on_field, on_file, boundary=boundary,
        config={"MAX_BODY_SIZE": limit, "MAX_MEMORY_FILE_SIZE": limit + 1},
    )
    try:
        parser.write(body)
        parser.finalize()
    except _BadRequest:
        raise
    except Exception:
        raise _BadRequest() from None
    if len(files) != 1 or files[0].field_name != b"audio" or not files[0].in_memory:
        raise _BadRequest()
    audio_file = files[0].file_object
    fields["audio"] = audio_file.getvalue()
    audio_file.close()
    return fields


@dataclass(frozen=True)
class _Authorized:
    live: LiveRoute
    token: str
    binding: object


def create_router(factory: Callable[[], Optional[LiveRoute]]) -> APIRouter:
    """Router for the credentialed routes, built around an explicit dependency factory."""
    live_state = _LazyLive(factory)
    router = APIRouter()
    in_flight = {"count": 0}

    def _denied() -> JSONResponse:
        return _respond(to_http(BoundaryFailure.create(ErrorCode.ACCESS_DENIED), service_auth_missing=True))

    def _invalid() -> JSONResponse:
        return _respond(to_http(BoundaryFailure.create(ErrorCode.INVALID_INPUT)))

    async def _authorize(request: Request, kind: ContextKind):
        """Settings, token and kind are all checked before any body byte is read (review fix 2)."""
        live = live_state.get()
        if live is None:
            return _respond(error_response(ErrorCode.NOT_CONFIGURED))
        token = _bearer(request)
        if token is None:
            return _denied()
        try:
            async with asyncio.timeout(live.limits.verify_timeout_seconds):
                claims = await live.verifier.inspect(token)
        except Exception:  # invalid, expired or unverifiable token (401): nothing reflected
            return _denied()
        if not live.verifier.is_usable(claims, kind):  # valid token, but reused or for another route (403)
            return _respond(to_http(BoundaryFailure.create(ErrorCode.ACCESS_DENIED)))
        return _Authorized(live=live, token=token, binding=claims.get("binding"))

    async def _guarded(request: Request, kind: ContextKind, work: Callable[[_Authorized], Awaitable[JSONResponse]]):
        authorized = await _authorize(request, kind)
        if not isinstance(authorized, _Authorized):
            return authorized
        # Bounded requests in flight per process, including body reads (review fix 2).
        if in_flight["count"] >= authorized.live.limits.max_concurrent_operations:
            return _respond(error_response(ErrorCode.CAPACITY_EXCEEDED))
        in_flight["count"] += 1
        try:
            return await work(authorized)
        finally:
            in_flight["count"] -= 1

    @router.post("/invoke")
    async def invoke(request: Request) -> JSONResponse:
        async def work(auth: _Authorized) -> JSONResponse:
            try:
                fields = _json_object(await _read_capped(request, JSON_BODY_LIMIT), INVOKE_FIELDS, frozenset({"generation_model"}))
            except _BadRequest:
                return _invalid()
            return _respond(to_http(await auth.live.handler.process(auth.token, auth.binding, fields)))

        return await _guarded(request, ContextKind.INVOKE, work)

    @router.post("/transcribe")
    async def transcribe(request: Request) -> JSONResponse:
        async def work(auth: _Authorized) -> JSONResponse:
            limit = auth.live.limits.max_audio_bytes + MULTIPART_OVERHEAD
            try:
                body = await _read_capped(request, limit)
                fields = _multipart_in_memory(request.headers.get("content-type", ""), body, limit)
            except _BadRequest:
                return _invalid()
            del body  # release the raw upload before the provider call
            required = {"audio", "audio_format", "transcription_model", "generation_model"}
            if not required <= set(fields):
                return _invalid()
            return _respond(to_http(await auth.live.handler.process(auth.token, auth.binding, fields)))

        return await _guarded(request, ContextKind.INVOKE, work)

    @router.post("/validate")
    async def validate(request: Request) -> JSONResponse:
        async def work(auth: _Authorized) -> JSONResponse:
            try:
                fields = _json_object(await _read_capped(request, JSON_BODY_LIMIT), VALIDATE_FIELDS, VALIDATE_FIELDS)
            except _BadRequest:
                return _invalid()
            return _respond(validation_to_http(await auth.live.handler.validate(auth.token, auth.binding, fields)))

        return await _guarded(request, ContextKind.VALIDATE, work)

    return router


router = create_router(lambda: build_from_environment(os.environ))
