"""T2.3 limit tests (TC-12 core): byte boundaries, shared capacity, deadlines, cleanup.

Deadlines use tiny test-only profiles (tens of milliseconds); nothing waits for
the real 90/20-second budgets.
"""

import asyncio
import dataclasses
import unittest

from services.provider_integration import (
    LOCAL_LIMIT_PROFILE,
    ContextKind,
    ErrorCode,
    Operation,
    Outcome,
    UsageEntry,
    ValidationStatus,
)
from services.provider_integration.orchestrator import AUDIO_INSTRUCTION, TRANSCRIPT_SEPARATOR

from fakes import FAST_LIMITS, Harness, PauseGate, Script, network_guard_patchers, wait_for_calls

SMALL_BYTES = dataclasses.replace(
    LOCAL_LIMIT_PROFILE,
    max_text_bytes=16,
    max_prompt_bytes=64,
    max_transcript_bytes=32,
    max_audio_bytes=8,
    max_generation_bytes=16,
)
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def utf8(text):
    return len(text.encode("utf-8"))


class ByteLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_boundaries(self):
        cases = [("a" * 15, True), ("é" * 8, True), ("é" * 8 + "a", False), (" " * 16 + "a", False)]
        for text, allowed in cases:
            with self.subTest(bytes=utf8(text)):
                h = Harness(limits=SMALL_BYTES)
                result = await h.orchestrator.invoke(h.context(), h.text_request(text))
                if allowed:
                    self.assertIs(result.outcome, Outcome.SUCCESS)
                else:
                    self.assertIs(result.error_code, ErrorCode.INVALID_INPUT)
                    self.assertEqual(h.store.admit_calls, 0)

    async def test_audio_boundaries(self):
        for size, allowed in ((7, True), (8, True), (9, False)):
            with self.subTest(size=size):
                h = Harness(limits=SMALL_BYTES)
                result = await h.orchestrator.invoke(h.context(), h.audio_request(audio=b"\x01" * size))
                self.assertEqual(result.outcome is Outcome.SUCCESS, allowed)
                if not allowed:
                    self.assertIs(result.error_code, ErrorCode.INVALID_INPUT)
                    self.assertEqual(h.store.admit_calls, 0)

    async def test_transcript_boundaries(self):
        for size, allowed in ((31, True), (32, True), (33, False)):
            with self.subTest(size=size):
                h = Harness(limits=dataclasses.replace(SMALL_BYTES, max_prompt_bytes=131_072))
                h.adapter.scripts["transcribe_audio"].append(Script(output="t" * size))
                result = await h.orchestrator.invoke(h.context(), h.audio_request())
                if allowed:
                    self.assertIs(result.outcome, Outcome.SUCCESS)
                else:
                    self.assertIs(result.error_code, ErrorCode.INVALID_INPUT)
                    self.assertEqual(h.adapter.calls_for("generate_text"), [])
                    self.assertEqual(result.usage, (UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe"),))

    async def test_prompt_boundaries(self):
        fixed = utf8(AUDIO_INSTRUCTION) + utf8(TRANSCRIPT_SEPARATOR)
        at_limit = SMALL_BYTES.max_prompt_bytes - fixed
        for size, allowed in ((at_limit - 1, True), (at_limit, True), (at_limit + 1, False)):
            with self.subTest(transcript_bytes=size):
                h = Harness(limits=SMALL_BYTES)
                h.adapter.scripts["transcribe_audio"].append(Script(output="p" * size))
                result = await h.orchestrator.invoke(h.context(), h.audio_request())
                if allowed:
                    self.assertIs(result.outcome, Outcome.SUCCESS)
                    self.assertEqual(utf8(h.adapter.calls_for("generate_text")[0].text), fixed + size)
                else:
                    self.assertIs(result.error_code, ErrorCode.INVALID_INPUT)
                    self.assertEqual(h.adapter.calls_for("generate_text"), [])

    async def test_generation_boundaries(self):
        cases = [("g" * 15, True), ("é" * 8, True), ("  " + "g" * 16 + "  ", True), ("g" * 17, False), ("é" * 8 + "g", False)]
        for output, allowed in cases:
            with self.subTest(output_bytes=utf8(output.strip())):
                h = Harness(limits=SMALL_BYTES)
                h.adapter.scripts["generate_text"].append(Script(output=output))
                result = await h.orchestrator.invoke(h.context(), h.text_request())
                if allowed:
                    self.assertEqual(result.result, output.strip())
                else:
                    self.assertIs(result.error_code, ErrorCode.PROVIDER_RESPONSE_INVALID)
                    self.assertIsNone(result.result)


class CapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_capacity_is_shared_and_non_queuing(self):
        h = Harness()
        gate = PauseGate()
        limit = h.config.limits.max_concurrent_operations
        self.assertEqual(limit, 8)
        h.adapter.scripts["generate_text"].extend(Script(gate=gate) for _ in range(limit))
        held = [asyncio.create_task(h.orchestrator.invoke(h.context(), h.text_request())) for _ in range(limit)]
        await wait_for_calls(h.adapter, limit, "generate_text")
        self.assertEqual(h.orchestrator.capacity_in_use, limit)

        ninth = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertIs(ninth.error_code, ErrorCode.CAPACITY_EXCEEDED)
        validation = await h.orchestrator.validate(h.context(kind=ContextKind.VALIDATE), h.validation_request())
        self.assertIs(validation.status, ValidationStatus.INDETERMINATE)
        self.assertIs(validation.reason_code, ErrorCode.CAPACITY_EXCEEDED)
        self.assertEqual(h.store.admit_calls, limit)
        self.assertEqual(validation.usage, ())

        gate.release.set()
        results = await asyncio.gather(*held)
        self.assertTrue(all(r.outcome is Outcome.SUCCESS for r in results))
        self.assertEqual(h.orchestrator.capacity_in_use, 0)
        self.assertIs((await h.orchestrator.invoke(h.context(), h.text_request())).outcome, Outcome.SUCCESS)


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def assertTimedOut(self, h, result, code):
        self.assertIs(result.error_code, code)
        self.assertIsNone(result.result)
        self.assertEqual(h.store.in_flight, 0)
        self.assertEqual(h.orchestrator.capacity_in_use, 0)
        self.assertEqual(h.adapter.sessions_opened, h.adapter.sessions_closed)

    async def test_admission_timeout(self):
        h = Harness(limits=FAST_LIMITS)
        h.store.admit_gate = PauseGate()  # never released
        result = await h.orchestrator.invoke(h.context(), h.text_request())
        await self.assertTimedOut(h, result, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(h.adapter.sessions_opened, 0)
        self.assertFalse(h.store.locked)

    async def test_step_timeouts_are_single_attempt(self):
        for stage in ("transcribe_audio", "generate_text"):
            with self.subTest(stage=stage):
                h = Harness(limits=FAST_LIMITS)
                h.adapter.scripts[stage].append(Script(hang=True))
                result = await h.orchestrator.invoke(h.context(), h.audio_request())
                await self.assertTimedOut(h, result, ErrorCode.PROVIDER_TIMEOUT)
                self.assertEqual(len(h.adapter.calls_for(stage)), 1)
                if stage == "transcribe_audio":
                    self.assertEqual(h.adapter.calls_for("generate_text"), [])
                self.assertIsNone(result.usage[-1].input_tokens)

    async def test_overall_deadline(self):
        loop = asyncio.get_running_loop()
        h = Harness(limits=FAST_LIMITS)
        h.adapter.scripts["generate_text"].append(Script(hang=True))
        started = loop.time() - FAST_LIMITS.invocation_timeout_seconds + 0.03  # 30 ms left < 100 ms call limit
        result = await h.orchestrator.invoke(h.context(), h.text_request(), started_at=started)
        await self.assertTimedOut(h, result, ErrorCode.OPERATION_TIMEOUT)
        self.assertLessEqual(h.adapter.calls_for("generate_text")[0].remaining_seconds, 0.03)

        h = Harness(limits=FAST_LIMITS)
        result = await h.orchestrator.invoke(h.context(), h.text_request(), started_at=loop.time() - 10)
        await self.assertTimedOut(h, result, ErrorCode.OPERATION_TIMEOUT)
        self.assertEqual(h.store.admit_calls, 0)

    async def test_remaining_time_passed_to_steps(self):
        h = Harness(limits=FAST_LIMITS)
        await h.orchestrator.invoke(h.context(), h.audio_request())
        for call in h.adapter.calls:
            with self.subTest(operation=call.operation):
                self.assertGreater(call.remaining_seconds, 0)
                self.assertLessEqual(call.remaining_seconds, 0.1)

    async def test_cleanup_is_bounded_and_releases(self):
        h = Harness(limits=FAST_LIMITS)
        h.adapter.close_hang = True
        result = await asyncio.wait_for(h.orchestrator.invoke(h.context(), h.text_request()), timeout=2)
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual(h.store.in_flight, 0)
        self.assertEqual(h.orchestrator.capacity_in_use, 0)


if __name__ == "__main__":
    unittest.main()
