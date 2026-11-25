"""T5.3: live credential reader (BackendCredentialReader).

Offline: the backend's resolve endpoint is simulated with httpx.MockTransport.
Includes a combined run through the real Orchestrator with a scripted adapter.
"""

import logging
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from services.provider_integration import (
    Binding,
    ContextKind,
    CredentialSource,
    CredentialState,
    ErrorCode,
    Operation,
    Outcome,
    Target,
    VerifiedContext,
)
from services.provider_integration.config import ModuleConfig
from services.provider_integration.errors import ProviderIntegrationError
from services.provider_integration.live.reader import BackendCredentialReader
from services.provider_integration.live.verifier import parse_binding_claim
from services.provider_integration.orchestrator import Orchestrator
from services.provider_integration.types import SecretValue

from fakes import LOCAL_LIMIT_PROFILE, Harness, ScriptedAdapter, make_provider_config
from live_fixtures import BINDING, GENERATE, PROVIDER_KEY, SCOPE_B, SERVICE_SECRET, TRANSCRIBE, FakeBackend, body_json, settings

GEN = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TR = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
TOKEN = "header.payload.signature-synthetic-token"


def context(kind=ContextKind.INVOKE, token=TOKEN, **binding_overrides):
    values = dict(BINDING)
    values.update(binding_overrides)
    binding = parse_binding_claim(values)  # the same conversion the live code uses (T5.6)
    return VerifiedContext(
        binding=binding, request_id="req-1", kind=kind, allowed_targets=frozenset({GEN, TR}),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        credential_token=SecretValue(token) if token else None,
    )


class ReaderTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = FakeBackend([])
        self.backend.resolve_ok()
        self.reader = BackendCredentialReader(settings(), transport=self.backend.transport())

    async def admit(self, ctx=None, targets=frozenset({GEN})):
        async with self.reader.admit(ctx or context(), targets) as lease:
            return lease

    async def assertFails(self, code, ctx=None):
        with self.assertRaises(ProviderIntegrationError) as caught:
            await self.admit(ctx)
        self.assertIs(caught.exception.code, code)
        text = repr(caught.exception) + str(caught.exception)
        for secret in (PROVIDER_KEY, TOKEN, SERVICE_SECRET):
            self.assertNotIn(secret, text)


class ResolveSuccessTests(ReaderTestCase):
    async def test_returns_exact_lease_with_redacted_key(self):
        lease = await self.admit()
        self.assertEqual(lease.binding, context().binding)
        self.assertIs(lease.state, CredentialState.ACTIVE)
        self.assertEqual(lease.permitted_targets, frozenset({GEN, TR}))
        self.assertEqual(lease.secret.reveal_for_session(), PROVIDER_KEY)
        self.assertNotIn(PROVIDER_KEY, repr(lease))

    async def test_request_carries_token_and_service_secret_only(self):
        await self.admit()
        request = self.backend.resolve_requests()[0]
        self.assertEqual(str(request.url), "https://backend.example.test/internal/credentials/resolve")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["authorization"], f"Bearer {SERVICE_SECRET}")
        self.assertEqual(body_json(request), {"context_token": TOKEN})

    async def test_pending_state_is_passed_through_for_the_orchestrator(self):
        self.backend.resolve_ok(state="pending")
        lease = await self.admit(context(kind=ContextKind.VALIDATE))
        self.assertIs(lease.state, CredentialState.PENDING)

    async def test_each_admission_calls_the_backend_again(self):
        await self.admit()
        await self.admit()
        self.assertEqual(len(self.backend.resolve_requests()), 2, "no cross-request key cache")


class ResolveFailureTests(ReaderTestCase):
    async def test_status_mapping(self):
        for status, code in ((401, ErrorCode.ACCESS_DENIED), (403, ErrorCode.ACCESS_DENIED),
                             (404, ErrorCode.CREDENTIAL_UNAVAILABLE), (409, ErrorCode.CREDENTIAL_UNAVAILABLE),
                             (500, ErrorCode.CREDENTIAL_UNAVAILABLE), (503, ErrorCode.CREDENTIAL_UNAVAILABLE),
                             (302, ErrorCode.CREDENTIAL_UNAVAILABLE)):
            with self.subTest(status=status):
                self.backend.resolve_status = status
                self.backend.resolve_body = {"error": f"detail with {PROVIDER_KEY}"}
                await self.assertFails(code)

    async def test_network_failures_are_unavailable(self):
        for error in (httpx.ConnectError("refused"), httpx.ReadTimeout("slow")):
            with self.subTest(error=type(error).__name__):
                self.backend.raise_error = error
                await self.assertFails(ErrorCode.CREDENTIAL_UNAVAILABLE)

    async def test_binding_mismatch_is_denied(self):
        for name, other in (("scope", dict(BINDING, scope_id=SCOPE_B)), ("version", dict(BINDING, credential_version=2)),
                            ("source", dict(BINDING, credential_source="platform"))):
            with self.subTest(case=name):
                self.backend.resolve_ok(binding=other)
                await self.assertFails(ErrorCode.ACCESS_DENIED)

    async def test_malformed_replies_are_unavailable(self):
        good = dict(binding=dict(BINDING), state="active", permitted_targets=[dict(GENERATE)], key=PROVIDER_KEY)
        cases = {
            "not an object": [1, 2],
            "extra field": dict(good, previous_key="test-provider-key-old"),
            "missing key": {k: v for k, v in good.items() if k != "key"},
            "empty key": dict(good, key=""),
            "padded key": dict(good, key=f" {PROVIDER_KEY}"),
            "numeric key": dict(good, key=123),
            "unknown state": dict(good, state="enabled"),
            "no targets": dict(good, permitted_targets=[]),
            "bad target": dict(good, permitted_targets=[{"operation": "x", "model": "y"}]),
        }
        for name, reply in cases.items():
            with self.subTest(case=name):
                self.backend.resolve_status = 200
                self.backend.resolve_body = reply
                await self.assertFails(ErrorCode.CREDENTIAL_UNAVAILABLE)

    async def test_invalid_json_and_oversized_replies(self):
        for name, raw, headers in (("not json", b"<html>", {}), ("oversized", b"{" + b" " * 70_000 + b"}", {}),
                                   ("compressed", b"{}", {"content-encoding": "gzip"})):
            with self.subTest(case=name):
                self.backend.resolve_status = 200
                self.backend.resolve_raw = raw
                self.backend.resolve_headers = headers
                await self.assertFails(ErrorCode.CREDENTIAL_UNAVAILABLE)

    async def test_missing_token_is_denied_without_calling_backend(self):
        await self.assertFails(ErrorCode.ACCESS_DENIED, context(token=None))
        self.assertEqual(self.backend.resolve_requests(), [])

    async def test_nothing_secret_is_logged(self):
        self.backend.resolve_status = 409
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger("reader-test").debug("marker")
            with self.assertRaises(ProviderIntegrationError):
                await self.admit()
            self.backend.resolve_ok()
            await self.admit()
        joined = "\n".join(captured.output)
        for secret in (PROVIDER_KEY, TOKEN, SERVICE_SECRET):
            self.assertNotIn(secret, joined)


class OrchestratorWithLiveReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoke_uses_the_resolved_key_once(self):
        backend = FakeBackend([])
        backend.resolve_ok()
        adapter = ScriptedAdapter(frozenset({GEN, TR}))
        orchestrator = Orchestrator(
            config=ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={"openai": make_provider_config()}),
            reader=BackendCredentialReader(settings(), transport=backend.transport()),
            adapters={"openai": adapter},
        )
        result = await orchestrator.invoke(context(), Harness.text_request())
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual([call.key for call in adapter.calls], [PROVIDER_KEY])
        self.assertEqual(len(backend.resolve_requests()), 1)

    async def test_disabled_version_is_never_used(self):
        backend = FakeBackend([])
        backend.resolve_status = 409
        adapter = ScriptedAdapter(frozenset({GEN, TR}))
        orchestrator = Orchestrator(
            config=ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={"openai": make_provider_config()}),
            reader=BackendCredentialReader(settings(), transport=backend.transport()),
            adapters={"openai": adapter},
        )
        result = await orchestrator.invoke(context(), Harness.text_request())
        self.assertIs(result.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(adapter.calls, [])


if __name__ == "__main__":
    unittest.main()


class ReplyVersionFormatTests(ReaderTestCase):
    """T5.6: the resolve reply's credential_version must be the same whole number as the token's."""

    async def test_numeric_reply_version_matches(self):
        lease = await self.admit()
        self.assertEqual(lease.binding.credential_version, "1")

    async def test_reply_with_other_version_types_is_unavailable(self):
        for name, version in (("text", "1"), ("zero", 0), ("boolean", True), ("decimal", 1.0)):
            with self.subTest(case=name):
                self.backend.resolve_ok(binding=dict(BINDING, credential_version=version))
                await self.assertFails(ErrorCode.CREDENTIAL_UNAVAILABLE)

    async def test_reply_for_another_version_is_denied(self):
        self.backend.resolve_ok(binding=dict(BINDING, credential_version=2))
        await self.assertFails(ErrorCode.ACCESS_DENIED)
