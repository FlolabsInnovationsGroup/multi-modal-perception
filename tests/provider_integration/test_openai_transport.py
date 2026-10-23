"""T3.2 transport tests (TC-09, TC-12 adapter): destination, redirects, headers, response cap.

Real SDK over httpx.MockTransport behind the adapter's GuardedTransport. Offline.
"""

import gzip
import json
import unittest
from unittest import mock

import httpx

from services.provider_integration import ErrorCode, ProviderOperationError
from services.provider_integration.adapters import openai as adapter_module
from services.provider_integration.adapters.openai import GuardedTransport, GuardViolation, OpenAIAdapter

from fakes import BOTH_TARGETS, GENERATE_TARGET, KEY_SCOPE_A, SYNTHETIC_DESTINATION, make_provider_config, network_guard_patchers
from test_openai_adapter import Recorder, chat_response, error_response, make_adapter, make_lease

_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def chat_body(content="Synthetic answer"):
    return json.dumps({
        "id": "chatcmpl-synthetic", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }).encode("utf-8")


def streamed(body, chunk_size=7, counter=None):
    async def generate():
        for start in range(0, len(body), chunk_size):
            chunk = body[start:start + chunk_size]
            if counter is not None:
                counter.append(len(chunk))
            yield chunk
    return httpx.Response(200, content=generate(), headers={"content-type": "application/json"})


class TransportTestCase(unittest.IsolatedAsyncioTestCase):
    async def generate(self, recorder, max_response_bytes=1_048_576, calls=1):
        adapter = make_adapter(recorder, max_response_bytes=max_response_bytes)
        outputs = []
        async with adapter.open_session(make_lease(), make_provider_config()) as session:
            for _ in range(calls):
                outputs.append(await session.generate_text(GENERATE_TARGET, "Hello", 5.0))
        return outputs

    async def assertGenerationFails(self, recorder, code, max_response_bytes=1_048_576):
        with self.assertRaises(ProviderOperationError) as caught:
            await self.generate(recorder, max_response_bytes)
        self.assertIs(caught.exception.code, code)
        self.assertNotIn(KEY_SCOPE_A, repr(caught.exception))
        return caught.exception


class DestinationAndRedirectTests(TransportTestCase):
    async def test_destination_redirect_and_environment(self):
        """TC-09: redirects are never followed; Location is never requested."""
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                recorder = Recorder(httpx.Response(status, headers={"location": "https://attacker.example.test/steal"}))
                await self.assertGenerationFails(recorder, ErrorCode.PROVIDER_RESPONSE_INVALID)
                self.assertEqual(len(recorder.requests), 1)
                self.assertEqual({r.url.host for r in recorder.requests}, {"provider.example.test"})

    async def test_guard_blocks_unapproved_urls_before_sending(self):
        recorder = Recorder()
        guard = GuardedTransport(recorder.transport(), SYNTHETIC_DESTINATION, 1024)
        blocked = [
            "https://attacker.example.test/v1/chat/completions",
            "http://provider.example.test/v1/chat/completions",
            "https://provider.example.test:8443/v1/chat/completions",
            "https://provider.example.test/v2/chat/completions",
            "https://provider.example.test/v1",
            "https://user:pass@provider.example.test/v1/chat/completions",
        ]
        for url in blocked:
            with self.subTest(url=url):
                guard.reset()
                with self.assertRaises(GuardViolation):
                    await guard.handle_async_request(httpx.Request("POST", url, headers={"authorization": f"Bearer {KEY_SCOPE_A}"}))
                self.assertTrue(guard.blocked)
        self.assertEqual(recorder.requests, [])
        for url in ("https://provider.example.test/v1/chat/completions", "https://provider.example.test:443/v1/audio/transcriptions"):
            with self.subTest(allowed=url):
                guard.reset()
                response = await guard.handle_async_request(httpx.Request("POST", url))
                await response.aread()
                self.assertFalse(guard.blocked)
        self.assertEqual(len(recorder.requests), 2)

    async def test_blocked_request_is_internal_error(self):
        """B3: if the SDK were pointed elsewhere, nothing is sent and the code is INTERNAL_ERROR."""
        recorder = Recorder()
        adapter = make_adapter(recorder)
        async with adapter.open_session(make_lease(), make_provider_config()) as session:
            session._client.base_url = "https://attacker.example.test/v1/"
            with self.assertRaises(ProviderOperationError) as caught:
                await session.generate_text(GENERATE_TARGET, "Hello", 5.0)
        self.assertIs(caught.exception.code, ErrorCode.INTERNAL_ERROR)
        self.assertEqual(recorder.requests, [])

    async def test_production_transport_settings(self):
        created = []

        class CapturingTransport(httpx.AsyncHTTPTransport):
            def __init__(self, *args, **kwargs):
                created.append(kwargs)
                super().__init__(*args, **kwargs)

        adapter = OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=5, max_response_bytes=1024)
        with mock.patch.object(adapter_module.httpx, "AsyncHTTPTransport", CapturingTransport):
            async with adapter.open_session(make_lease(), make_provider_config()) as session:
                self.assertIsInstance(session._guard, GuardedTransport)
                self.assertIsInstance(session._guard._inner, CapturingTransport)
        self.assertEqual(created, [{"verify": True, "trust_env": False, "retries": 0}])


class HeaderTests(TransportTestCase):
    async def test_header_hygiene(self):
        """B2/B4: org/project headers removed and identity encoding forced at the transport."""
        recorder = Recorder()
        guard = GuardedTransport(recorder.transport(), SYNTHETIC_DESTINATION, 4096)
        request = httpx.Request("POST", SYNTHETIC_DESTINATION + "chat/completions", headers={
            "OpenAI-Organization": "org-forced", "OpenAI-Project": "proj-forced", "Accept-Encoding": "gzip, br",
        })
        response = await guard.handle_async_request(request)
        await response.aread()
        sent = recorder.requests[0].headers
        self.assertNotIn("openai-organization", sent)
        self.assertNotIn("openai-project", sent)
        self.assertEqual(sent["accept-encoding"], "identity")

    async def test_forced_organization_never_sent_end_to_end(self):
        recorder = Recorder(chat_response())
        async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
            session._client.organization = "org-forced"
            session._client.project = "proj-forced"
            await session.generate_text(GENERATE_TARGET, "Hello", 5.0)
        headers = recorder.requests[0].headers
        self.assertNotIn("openai-organization", headers)
        self.assertNotIn("openai-project", headers)
        self.assertEqual(headers["accept-encoding"], "identity")

    async def test_compressed_response_refused(self):
        for encoding in ("gzip", "br", "deflate"):
            with self.subTest(encoding=encoding):
                pulled = []
                response = streamed(gzip.compress(chat_body()), counter=pulled)  # streamed: no eager decoding
                response.headers["content-encoding"] = encoding
                await self.assertGenerationFails(Recorder(response), ErrorCode.PROVIDER_RESPONSE_INVALID)
                self.assertEqual(sum(pulled), 0)  # refused before reading


class ResponseCapTests(TransportTestCase):
    async def test_response_cap(self):
        """TC-12 (adapter): N-1/N/N+1 with declared length and with streamed bodies."""
        body = chat_body()
        size = len(body)
        for label, make in (
            ("declared", lambda: httpx.Response(200, content=body, headers={"content-type": "application/json"})),
            ("streamed", lambda: streamed(body)),
        ):
            for cap, allowed in ((size + 1, True), (size, True), (size - 1, False)):
                with self.subTest(body=label, cap_minus_size=cap - size):
                    recorder = Recorder(make())
                    if allowed:
                        outputs = await self.generate(recorder, max_response_bytes=cap)
                        self.assertEqual(outputs[0].text, "Synthetic answer")
                    else:
                        await self.assertGenerationFails(recorder, ErrorCode.PROVIDER_RESPONSE_INVALID, cap)
                    self.assertEqual(len(recorder.requests), 1)

    async def test_oversized_stream_stops_early(self):
        pulled = []
        huge = b"x" * (10 * 1024 * 1024)
        recorder = Recorder(streamed(huge, chunk_size=1024, counter=pulled))
        await self.assertGenerationFails(recorder, ErrorCode.PROVIDER_RESPONSE_INVALID, max_response_bytes=4096)
        self.assertLessEqual(sum(pulled), 4096 + 1024)

    async def test_declared_oversize_is_not_read(self):
        pulled = []
        response = streamed(b"y" * 8192, chunk_size=1024, counter=pulled)
        response.headers["content-length"] = "8192"
        await self.assertGenerationFails(Recorder(response), ErrorCode.PROVIDER_RESPONSE_INVALID, max_response_bytes=4096)
        self.assertEqual(sum(pulled), 0)

    async def test_error_bodies_are_capped(self):
        response = httpx.Response(500, content=b"z" * 8192, headers={"content-type": "application/json"})
        await self.assertGenerationFails(Recorder(response), ErrorCode.PROVIDER_RESPONSE_INVALID, max_response_bytes=4096)

    async def test_cap_counts_each_request_separately(self):
        body = chat_body()
        recorder = Recorder(
            httpx.Response(200, content=body, headers={"content-type": "application/json"}),
            httpx.Response(200, content=body, headers={"content-type": "application/json"}),
        )
        outputs = await self.generate(recorder, max_response_bytes=len(body), calls=2)
        self.assertEqual([o.text for o in outputs], ["Synthetic answer", "Synthetic answer"])

    async def test_cap_does_not_hide_normal_error_mapping(self):
        await self.assertGenerationFails(Recorder(error_response(429, "rate_limit_exceeded")), ErrorCode.RATE_LIMITED)


if __name__ == "__main__":
    unittest.main()
