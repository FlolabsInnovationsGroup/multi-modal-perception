"""Smoke tests for the existing routes: /health, /process, /openAI and the API docs.

Added with the security update of 2026-11-18 (FastAPI 0.162, Starlette 1.10,
Pydantic 2.14, python-multipart 0.0.33) to prove the routes behave as before.
The OpenAI service is replaced by a fake; keys are synthetic. The service key
header is always sent, so the tests also pass where the short-term key check
is installed.

Run from the repository root:
    python -m unittest discover -s tests -p "test_legacy_routes.py"
"""

import os
import unittest
from unittest import mock

import httpx

import main
from api import openAI as openai_route
from api import process as process_route

KEY = "test-service-key-redacted-0123456789abcdef"
AUDIO = b"RIFF-synthetic" * 200_000  # about 2.8 MB, larger than the framework's 1 MiB spool size


class FakeService:
    def __init__(self):
        self.calls = []

    async def generate_multimodal_response(self, **kwargs):
        self.calls.append(kwargs)
        return "Synthetic answer", 7


class LegacyRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake = FakeService()
        for patcher in (mock.patch.dict(os.environ, {"MULTIMODAL_API_KEY": KEY}),
                        mock.patch.object(process_route, "get_ultra_fast_service", return_value=self.fake),
                        mock.patch.object(openai_route, "get_ultra_fast_service", return_value=self.fake)):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def request(self, method, path, **kwargs):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
            return await client.request(method, path, headers={"Authorization": f"Bearer {KEY}"}, **kwargs)

    async def test_text_audio_and_missing_input(self):
        for path in ("/process", "/openAI"):
            with self.subTest(path=path, case="text"):
                response = await self.request("POST", path, data={"text_input": "Hello"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(set(response.json()), {"result", "model", "file_type"})
                self.assertEqual((response.json()["result"], response.json()["file_type"]), ("Synthetic answer", "text"))
            with self.subTest(path=path, case="text and audio"):
                response = await self.request("POST", path, data={"text_input": "Summarize"},
                                              files={"audio_file": ("a.wav", AUDIO, "audio/wav")})
                self.assertEqual((response.status_code, response.json()["file_type"]), (200, "audio"), response.text)
                self.assertEqual(self.fake.calls[-1]["audio_bytes"], AUDIO)
                self.assertEqual(self.fake.calls[-1]["audio_filename"], "a.wav")
            with self.subTest(path=path, case="audio only"):
                response = await self.request("POST", path, files={"audio_file": ("b.mp3", b"ID3-synthetic", "audio/mpeg")})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.fake.calls[-1]["text_input"], "reply to the audio")
            with self.subTest(path=path, case="missing input"):
                response = await self.request("POST", path, data={})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"], "Provide at least one of text_input or audio_file.")

    async def test_health_docs_and_openapi(self):
        self.assertEqual((await self.request("GET", "/health")).json(), {"status": "healthy"})
        spec = await self.request("GET", "/openapi.json")
        self.assertEqual(spec.status_code, 200)
        self.assertTrue({"/health", "/process", "/openAI"} <= set(spec.json()["paths"]))
        self.assertEqual((await self.request("GET", "/docs")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
