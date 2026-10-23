"""T4.2 isolation tests (TC-03): full stack with the real adapter over a mocked transport.

handler -> fake verifier/store -> orchestrator -> OpenAIAdapter -> httpx.MockTransport.
Overlap is forced with barriers/gates inside the transport, not timing.
"""

import asyncio
import json
import unittest

import httpx

from services.provider_integration import LOCAL_LIMIT_PROFILE, ContextKind, ErrorCode, Outcome, ValidationStatus
from services.provider_integration.adapters.openai import OpenAIAdapter
from services.provider_integration.handler import Handler
from services.provider_integration.orchestrator import Orchestrator

from fakes import (
    BOTH_TARGETS,
    KEY_SCOPE_A,
    KEY_SCOPE_A_V2,
    KEY_SCOPE_B,
    FakeContextVerifier,
    Harness,
    PauseGate,
    network_guard_patchers,
)
from test_openai_adapter import CapturingClient, capture_clients

_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def binding_fields(scope="scope-A", ref="credential-A", version="v1"):
    return dict(scope_id=scope, credential_ref=ref, credential_version=version,
                credential_source="customer", provider="openai")


def text_request(text):
    return dict(text=text, generation_model="gpt-4o-mini")


VALIDATE_TEXT = {"operation": "generate_text", "model": "gpt-4o-mini"}


def chat_json(content):
    return {
        "id": "chatcmpl-synthetic", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


class KeyedProvider:
    """Async MockTransport handler: answers per key; optional barrier/gate to force overlap."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []
        self.barrier = None
        self.gates = {}

    async def __call__(self, request):
        await request.aread()
        self.requests.append(request)
        key = request.headers["authorization"].removeprefix("Bearer ")
        if self.barrier is not None:
            await self.barrier.wait()
        gate = self.gates.pop(key, None)
        if gate is not None:
            await gate.pause()
        return httpx.Response(200, json=chat_json(self.answers.get(key, "unknown key")), headers={"x-request-id": "req_iso"})

    def keys(self):
        return [r.headers["authorization"].removeprefix("Bearer ") for r in self.requests]


class Stack:
    """Full local stack with explicit dependencies (test-only composition)."""

    def __init__(self, provider, limits=LOCAL_LIMIT_PROFILE, reader_factory=None):
        self.h = Harness(limits=limits, reader_factory=reader_factory)
        self.provider = provider
        self.adapter = OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=limits.connect_timeout_seconds,
                                     max_response_bytes=limits.max_response_body_bytes,
                                     transport=httpx.MockTransport(provider))
        self.orchestrator = Orchestrator(config=self.h.config, reader=self.h.reader,
                                         adapters={"openai": self.adapter}, utc_now=self.h.clock.now)
        self.verifier = FakeContextVerifier(self.h.clock)
        self.handler = Handler(verifier=self.verifier, orchestrator=self.orchestrator, limits=limits)
        for scope, ref in (("scope-A", "credential-A"), ("scope-B", "credential-B")):
            self.verifier.register(f"invoke-{scope}", self.h.context(scope_id=scope, credential_ref=ref))
            self.verifier.register(f"validate-{scope}", self.h.context(kind=ContextKind.VALIDATE, scope_id=scope, credential_ref=ref))

    def assertReleased(self, test):
        test.assertEqual((self.h.store.in_flight, self.orchestrator.capacity_in_use), (0, 0))


class IsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_scopes_same_prompt(self):
        """TC-03: overlapping identical prompts never share key, client, session or answer."""
        provider = KeyedProvider({KEY_SCOPE_A: "answer for A", KEY_SCOPE_B: "answer for B"})
        provider.barrier = asyncio.Barrier(2)
        stack = Stack(provider)
        with capture_clients():
            result_a, result_b = await asyncio.gather(
                stack.handler.process("invoke-scope-A", binding_fields(), text_request("Same prompt")),
                stack.handler.process("invoke-scope-B", binding_fields("scope-B", "credential-B"), text_request("Same prompt")),
            )
            clients = [client for client, _ in CapturingClient.created]
            provider.barrier = None
            again = await stack.handler.process("invoke-scope-A", binding_fields(), text_request("Same prompt"))
        self.assertEqual((result_a.result, result_b.result, again.result), ("answer for A", "answer for B", "answer for A"))
        self.assertEqual((result_a.request_id == result_b.request_id), False)
        self.assertEqual(sorted(provider.keys()[:2]), sorted([KEY_SCOPE_A, KEY_SCOPE_B]))
        self.assertEqual(provider.keys()[2], KEY_SCOPE_A)  # repeat request reaches the provider again
        self.assertEqual(len(clients), 2)
        self.assertIsNot(clients[0], clients[1])
        self.assertTrue(all(client.is_closed for client, _ in CapturingClient.created))
        for request in provider.requests:
            self.assertEqual(json.loads(request.content)["messages"][-1]["content"], "Same prompt")
        stack.assertReleased(self)

    async def test_interleaved_invoke_and_validate(self):
        provider = KeyedProvider({KEY_SCOPE_A: "OK", KEY_SCOPE_B: "OK"})
        provider.barrier = asyncio.Barrier(3)
        stack = Stack(provider)
        invoke_a, validate_b, validate_a = await asyncio.gather(
            stack.handler.process("invoke-scope-A", binding_fields(), text_request("Hello")),
            stack.handler.validate("validate-scope-B", binding_fields("scope-B", "credential-B"), VALIDATE_TEXT),
            stack.handler.validate("validate-scope-A", binding_fields(), VALIDATE_TEXT),
        )
        self.assertIs(invoke_a.outcome, Outcome.SUCCESS)
        self.assertEqual((validate_b.status, validate_a.status), (ValidationStatus.VALID, ValidationStatus.VALID))
        self.assertEqual((validate_b.binding.scope_id, validate_a.binding.scope_id), ("scope-B", "scope-A"))
        self.assertEqual(sorted(provider.keys()), sorted([KEY_SCOPE_A, KEY_SCOPE_A, KEY_SCOPE_B]))
        bodies = {r.headers["authorization"]: json.loads(r.content) for r in provider.requests}
        probe = bodies[f"Bearer {KEY_SCOPE_B}"]
        self.assertEqual(probe["messages"], [{"role": "user", "content": "Reply with OK."}])
        stack.assertReleased(self)

    async def test_rotation_mid_flight(self):
        """C3 end to end: an in-flight v1 request finishes with v1; later v1 requests are denied."""
        provider = KeyedProvider({KEY_SCOPE_A: "answer v1", KEY_SCOPE_A_V2: "answer v2"})
        gate = PauseGate()
        provider.gates[KEY_SCOPE_A] = gate
        stack = Stack(provider)
        await stack.h.store.add_pending("scope-A", "credential-A", "v2", key=KEY_SCOPE_A_V2, targets=BOTH_TARGETS)

        held = asyncio.create_task(stack.handler.process("invoke-scope-A", binding_fields(), text_request("Hello")))
        await gate.entered.wait()
        await stack.h.store.rotate("scope-A", "credential-A", "v2")
        gate.release.set()
        first = await held
        self.assertEqual(first.result, "answer v1")

        stale = await stack.handler.process("invoke-scope-A", binding_fields(), text_request("Hello"))
        self.assertIs(stale.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        stack.verifier.register("invoke-v2", stack.h.context(credential_version="v2"))
        fresh = await stack.handler.process("invoke-v2", binding_fields(version="v2"), text_request("Hello"))
        self.assertEqual(fresh.result, "answer v2")
        self.assertEqual(provider.keys(), [KEY_SCOPE_A, KEY_SCOPE_A_V2])  # the stale request never reached the provider
        stack.assertReleased(self)


if __name__ == "__main__":
    unittest.main()
