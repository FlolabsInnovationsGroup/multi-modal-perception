"""T4.2 leakage tests (TC-08): key and content canaries across every exit path.

Full stack with the real adapter over httpx.MockTransport. Each scenario is
watched for canaries in results, serializations, log records (INFO and up),
warnings, the asyncio exception handler and file writes (via an audit hook
that only records while a scenario is active; E1).
"""

import asyncio
import dataclasses
import json
import logging
import pickle
import sys
import traceback
import unittest
import warnings

import httpx

from services.provider_integration import BoundaryFailure, ContextKind, ErrorCode, Outcome
from services.provider_integration.handler import legacy_success

from fakes import BOTH_TARGETS, Harness, PauseGate, RaisingReader, network_guard_patchers
from test_isolation import Stack, binding_fields, chat_json

KEY_CANARY = "test-provider-key-leak-canary-7c1e"
CONTENT_CANARY = "CONTENT-CANARY-5d2a"
CANARIES = (KEY_CANARY, CONTENT_CANARY)
_patches = []

# --- file-write audit (E1) -----------------------------------------------------

_AUDIT = {"active": False, "writes": []}
_WRITE_FLAGS = 0
for _name in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"):
    _WRITE_FLAGS |= getattr(__import__("os"), _name, 0)


def _audit(event, args):
    if not _AUDIT["active"]:
        return
    if event == "open" and args:
        path, mode, flags = (list(args) + [None, None, None])[:3]
        path_text = str(path)
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & _WRITE_FLAGS)
        if writing and not path_text.endswith(".pyc") and "__pycache__" not in path_text:
            _AUDIT["writes"].append(path_text)
    elif event.startswith("tempfile."):
        _AUDIT["writes"].append(event)


sys.addaudithook(_audit)  # cannot be removed; inert unless a scenario is being watched


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.rendered = []
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record):
        self.rendered.append(self.format(record))


class Watch:
    """Collects every observable side channel while a scenario runs."""

    def __init__(self, level=logging.INFO):
        self.level = level
        self.logs = _Capture()
        self.loop_errors = []

    async def __aenter__(self):
        self._root = logging.getLogger()
        self._previous = self._root.level
        self._root.setLevel(self.level)
        self._root.addHandler(self.logs)
        self._warnings = warnings.catch_warnings(record=True)
        self.warned = self._warnings.__enter__()
        warnings.simplefilter("always")
        self._loop = asyncio.get_running_loop()
        self._previous_handler = self._loop.get_exception_handler()
        self._loop.set_exception_handler(lambda loop, context: self.loop_errors.append(repr(context)))
        _AUDIT["writes"].clear()
        _AUDIT["active"] = True
        return self

    async def __aexit__(self, *exc):
        _AUDIT["active"] = False
        self._loop.set_exception_handler(self._previous_handler)
        self._warnings.__exit__(None, None, None)
        self._root.removeHandler(self.logs)
        self._root.setLevel(self._previous)
        return False

    def channels(self):
        return {
            "logs": "\n".join(self.logs.rendered),
            "warnings": "\n".join(str(w.message) for w in self.warned),
            "loop": "\n".join(self.loop_errors),
            "files": "\n".join(_AUDIT["writes"]),
        }


def render(result):
    parts = [repr(result), str(result)]
    if dataclasses.is_dataclass(result):
        parts.append(json.dumps(dataclasses.asdict(result), default=str))
        parts.append(repr(pickle.loads(pickle.dumps(result))))
    return "\n".join(parts)


class LeakProvider:
    """MockTransport handler whose failures echo both canaries back."""

    def __init__(self, mode):
        self.mode = mode
        self.requests = []
        self.gate = PauseGate()

    async def __call__(self, request):
        body = await request.aread()
        self.requests.append(body)
        echo = f"{KEY_CANARY} {CONTENT_CANARY}"
        if self.mode == "success":
            return httpx.Response(200, json=chat_json("Synthetic answer"))
        if self.mode == "transcript":
            if b"transcriptions" in request.url.raw_path:
                return httpx.Response(200, json={"text": f"heard {CONTENT_CANARY}"})
            return httpx.Response(200, json=chat_json("Synthetic answer"))
        if self.mode == "401":
            return httpx.Response(401, json={"error": {"message": echo, "type": "invalid_request_error", "code": "invalid_api_key"}})
        if self.mode == "500":
            return httpx.Response(500, json={"error": {"message": echo, "type": "server_error", "code": None}})
        if self.mode == "connect":
            raise httpx.ConnectError(f"cannot connect {echo}")
        if self.mode == "timeout":
            raise httpx.ReadTimeout(f"timed out {echo}")
        if self.mode == "oversized":
            return httpx.Response(200, content=(echo * 100_000).encode())
        if self.mode == "malformed":
            return httpx.Response(200, content=f"not json {echo}".encode())
        if self.mode == "key-in-output":
            return httpx.Response(200, json=chat_json(f"here is the key {KEY_CANARY}"))
        if self.mode == "hang":
            await self.gate.pause()
        raise AssertionError("unknown mode")


def leak_stack(mode, reader_factory=None):
    provider = LeakProvider(mode)
    stack = Stack(provider, reader_factory=reader_factory)
    stack.h.store.add_record("scope-L", "credential-L", "v1", key=KEY_CANARY, targets=BOTH_TARGETS, active=True)
    stack.verifier.register("invoke-L", stack.h.context(scope_id="scope-L", credential_ref="credential-L"))
    stack.verifier.register("validate-L", stack.h.context(kind=ContextKind.VALIDATE, scope_id="scope-L", credential_ref="credential-L"))
    return stack, provider


LEAK_BINDING = binding_fields("scope-L", "credential-L")
TEXT = dict(text=f"please summarize {CONTENT_CANARY}", generation_model="gpt-4o-mini")
AUDIO = dict(text="", audio=f"RIFF {CONTENT_CANARY}".encode(), audio_format="wav",
             generation_model="gpt-4o-mini", transcription_model="gpt-4o-mini-transcribe")


class LeakageTests(unittest.IsolatedAsyncioTestCase):
    def assertClean(self, watch, result_text, allow_content_in_result=False):
        for name, text in watch.channels().items():
            for canary in CANARIES:
                with self.subTest(channel=name, canary=canary[:12]):
                    self.assertNotIn(canary, text)
        self.assertEqual(watch.channels()["files"], "")
        self.assertNotIn(KEY_CANARY, result_text)
        if not allow_content_in_result:
            self.assertNotIn(CONTENT_CANARY, result_text)

    async def warm_up(self):
        """Import lazily loaded SDK/pydantic modules before watching file writes."""
        stack, _ = leak_stack("success")
        legacy_success(await stack.handler.process("invoke-L", LEAK_BINDING, TEXT))

    async def test_canary_all_exits(self):
        """TC-08: no canary in any non-content channel for any exit path."""
        await self.warm_up()
        scenarios = [
            ("success text", "success", TEXT, Outcome.SUCCESS),
            ("success audio, canary transcript", "transcript", AUDIO, Outcome.SUCCESS),
            ("401 echoing key", "401", TEXT, ErrorCode.CREDENTIAL_REJECTED),
            ("500 echoing key", "500", TEXT, ErrorCode.PROVIDER_UNAVAILABLE),
            ("connection error with key", "connect", TEXT, ErrorCode.PROVIDER_UNAVAILABLE),
            ("timeout with key", "timeout", TEXT, ErrorCode.PROVIDER_TIMEOUT),
            ("oversized body", "oversized", TEXT, ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("malformed body", "malformed", TEXT, ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("key in model output", "key-in-output", TEXT, ErrorCode.INTERNAL_ERROR),
        ]
        for name, mode, request, expected in scenarios:
            with self.subTest(scenario=name):
                stack, provider = leak_stack(mode)
                async with Watch() as watch:
                    result = await stack.handler.process("invoke-L", LEAK_BINDING, request)
                    rendered = render(result)
                    if result.outcome is Outcome.SUCCESS:
                        rendered += repr(legacy_success(result))
                if expected is Outcome.SUCCESS:
                    self.assertIs(result.outcome, Outcome.SUCCESS)
                else:
                    self.assertIs(result.error_code, expected)
                self.assertClean(watch, rendered)
                self.assertTrue(any(CONTENT_CANARY.encode() in body for body in provider.requests))  # content reached the provider only
                stack.assertReleased(self)

    async def test_validation_and_boundary_paths(self):
        await self.warm_up()
        stack, _ = leak_stack("401")
        async with Watch() as watch:
            validation = await stack.handler.validate("validate-L", LEAK_BINDING, {"operation": "generate_text", "model": "gpt-4o-mini"})
            rendered = render(validation)
        self.assertEqual(validation.reason_code, ErrorCode.CREDENTIAL_REJECTED)
        self.assertClean(watch, rendered)

        class LeakyVerifier:
            async def verify(self, *args):
                raise RuntimeError(f"verifier {KEY_CANARY} {CONTENT_CANARY}")

        stack, _ = leak_stack("success")
        stack.handler._verifier = LeakyVerifier()
        async with Watch() as watch:
            boundary = await stack.handler.process("invoke-L", LEAK_BINDING, TEXT)
            rendered = render(boundary)
        self.assertIsInstance(boundary, BoundaryFailure)
        self.assertClean(watch, rendered)

        stack, provider = leak_stack("success", reader_factory=lambda store: RaisingReader(f"reader {KEY_CANARY}"))
        stack.verifier.register("invoke-L", stack.h.context(scope_id="scope-L", credential_ref="credential-L"))
        async with Watch() as watch:
            outage = await stack.handler.process("invoke-L", LEAK_BINDING, TEXT)
            rendered = render(outage)
        self.assertIs(outage.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(provider.requests, [])
        self.assertClean(watch, rendered)

    async def test_cancellation_leaks_nothing(self):
        await self.warm_up()
        stack, provider = leak_stack("hang")
        async with Watch() as watch:
            task = asyncio.create_task(stack.handler.process("invoke-L", LEAK_BINDING, TEXT))
            await provider.gate.entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError) as caught:
                await task
            rendered = "".join(traceback.format_exception(caught.exception))
        self.assertClean(watch, rendered)
        stack.assertReleased(self)

    async def test_debug_logging_fails_closed_without_logging_content(self):
        """A3 end to end: with SDK debug logging on, nothing is sent and nothing sensitive is logged."""
        await self.warm_up()
        stack, provider = leak_stack("success")
        async with Watch(level=logging.DEBUG) as watch:
            result = await stack.handler.process("invoke-L", LEAK_BINDING, TEXT)
            rendered = render(result)
        self.assertIs(result.error_code, ErrorCode.NOT_CONFIGURED)
        self.assertEqual(provider.requests, [])
        self.assertClean(watch, rendered)

    async def test_watch_detects_leaks(self):
        """Positive control: every watched channel really reports a planted canary."""
        import tempfile

        async with Watch() as watch:
            logging.getLogger("services.provider_integration").warning("planted %s", CONTENT_CANARY)
            warnings.warn(f"planted {KEY_CANARY}")
            asyncio.get_running_loop().call_exception_handler({"message": f"planted {CONTENT_CANARY}"})
            with tempfile.NamedTemporaryFile("w", delete=True) as handle:
                handle.write("x")
        channels = watch.channels()
        self.assertIn(CONTENT_CANARY, channels["logs"])
        self.assertIn(KEY_CANARY, channels["warnings"])
        self.assertIn(CONTENT_CANARY, channels["loop"])
        self.assertNotEqual(channels["files"], "")

    def test_secret_objects_refuse_serialization(self):
        lease_store = Harness().store
        lease_store.add_record("scope-L", "credential-L", "v1", key=KEY_CANARY, targets=BOTH_TARGETS, active=True)
        from services.provider_integration import SecretValue

        secret = SecretValue(KEY_CANARY)
        for dump in (lambda: pickle.dumps(secret), lambda: json.dumps(secret)):
            with self.assertRaises(TypeError):
                dump()
        self.assertNotIn(KEY_CANARY, repr(secret) + str(secret) + f"{secret}")


if __name__ == "__main__":
    unittest.main()
