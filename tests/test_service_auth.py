"""Short-term service key check for the live routes.

Every route except /health requires ``Authorization: Bearer <MULTIMODAL_API_KEY>``.
The check runs before the request body is read, fails closed when the key is
missing or weak, and never logs or returns the key.

Offline only: the OpenAI service is replaced by a fake, and requests go through
httpx's in-process ASGI transport. Keys are synthetic placeholders.

Run from the repository root:
    python -m unittest discover -s tests -p "test_service_auth.py"
"""

import logging
import os
import unittest
from unittest import mock

import httpx

import main
from api import openAI as openai_route
from api import process as process_route
from api.service_auth import ENV_VAR, MIN_KEY_LENGTH, ServiceKeyMiddleware

SERVICE_KEY = "test-service-key-redacted-0123456789abcdef"
WRONG_KEY = "test-service-key-wrong-0123456789abcdefghij"
OPENAI_CANARY = "test-provider-key-must-not-be-used"


class FakeService:
    def __init__(self):
        self.calls = 0

    async def generate_multimodal_response(self, **kwargs):
        self.calls += 1
        return "Synthetic answer", 7


class ServiceKeyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake = FakeService()
        patchers = [
            mock.patch.dict(os.environ, {ENV_VAR: SERVICE_KEY, "OPENAI_API_KEY": OPENAI_CANARY}),
            mock.patch.object(process_route, "get_ultra_fast_service", return_value=self.fake),
            mock.patch.object(openai_route, "get_ultra_fast_service", return_value=self.fake),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def post(self, path="/process", headers=None, data=None, files=None):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
            return await client.post(path, headers=headers or {}, data=data or {"text_input": "Hello"}, files=files)

    async def get(self, path, headers=None):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
            return await client.get(path, headers=headers or {})

    def assertRejected(self, response, status=401):
        self.assertEqual(response.status_code, status)
        self.assertEqual(self.fake.calls, 0, "the provider must not be called")
        text = response.text + repr(response.headers)
        for secret in (SERVICE_KEY, WRONG_KEY, OPENAI_CANARY):
            self.assertNotIn(secret, text)

    # -- accepted ---------------------------------------------------------------

    async def test_correct_key_reaches_both_routes_unchanged(self):
        for path in ("/process", "/openAI"):
            with self.subTest(path=path):
                response = await self.post(path, headers={"Authorization": f"Bearer {SERVICE_KEY}"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"result": "Synthetic answer", "model": main_model(), "file_type": "text"})

    async def test_scheme_is_case_insensitive(self):
        response = await self.post(headers={"Authorization": f"bearer {SERVICE_KEY}"})
        self.assertEqual(response.status_code, 200)

    async def test_health_stays_open(self):
        response = await self.get("/health")
        self.assertEqual((response.status_code, response.json()), (200, {"status": "healthy"}))

    # -- rejected ---------------------------------------------------------------

    async def test_missing_wrong_and_malformed_keys_are_rejected(self):
        cases = {
            "no header": {},
            "wrong key": {"Authorization": f"Bearer {WRONG_KEY}"},
            "key prefix only": {"Authorization": f"Bearer {SERVICE_KEY[:-1]}"},
            "key plus extra": {"Authorization": f"Bearer {SERVICE_KEY}x"},
            "trailing space": {"Authorization": f"Bearer {SERVICE_KEY} "},
            "double space": {"Authorization": f"Bearer  {SERVICE_KEY}"},
            "wrong scheme": {"Authorization": f"Basic {SERVICE_KEY}"},
            "no scheme": {"Authorization": SERVICE_KEY},
            "empty bearer": {"Authorization": "Bearer "},
            "other header": {"X-Api-Key": SERVICE_KEY},
        }
        for name, headers in cases.items():
            with self.subTest(case=name):
                response = await self.post(headers=headers)
                self.assertRejected(response)
                self.assertEqual(response.json(), {"detail": "Unauthorized"})
                self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    async def test_two_authorization_headers_are_rejected(self):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
            request = client.build_request("POST", "/process", data={"text_input": "Hello"})
            request.headers = httpx.Headers([*request.headers.multi_items(),
                                             ("Authorization", f"Bearer {SERVICE_KEY}"),
                                             ("Authorization", f"Bearer {SERVICE_KEY}")])
            response = await client.send(request)
        self.assertRejected(response)

    async def test_every_other_route_is_protected(self):
        for method, path in (("POST", "/openAI"), ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"),
                             ("GET", "/process"), ("GET", "/unknown")):
            with self.subTest(path=path, method=method):
                response = await (self.get(path) if method == "GET" else self.post(path))
                self.assertRejected(response)

    async def test_unconfigured_or_weak_key_fails_closed(self):
        for name, value in (("missing", None), ("empty", ""), ("short", "s" * (MIN_KEY_LENGTH - 1)),
                            ("whitespace", f" {SERVICE_KEY}"), ("non-ascii", "k" * MIN_KEY_LENGTH + "é")):
            with self.subTest(config=name):
                env = {k: v for k, v in os.environ.items() if k != ENV_VAR}
                if value is not None:
                    env[ENV_VAR] = value
                with mock.patch.dict(os.environ, env, clear=True):
                    sent = value.strip() if value and value.isascii() else SERVICE_KEY
                    response = await self.post(headers={"Authorization": f"Bearer {sent}"})
                    self.assertRejected(response, status=503)
                    self.assertEqual(response.json(), {"detail": "Service authentication is not configured."})
                    health = await self.get("/health")
                    self.assertEqual(health.status_code, 200)

    async def test_minimum_length_key_is_accepted(self):
        key = "m" * MIN_KEY_LENGTH
        with mock.patch.dict(os.environ, {ENV_VAR: key}):
            response = await self.post(headers={"Authorization": f"Bearer {key}"})
        self.assertEqual(response.status_code, 200)

    # -- ordering and leakage ------------------------------------------------------

    async def test_rejected_request_body_is_never_read(self):
        received = []
        sent = []

        async def receive():
            received.append(True)
            return {"type": "http.request", "body": b"x" * 1024, "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": "/process", "raw_path": b"/process", "root_path": "", "query_string": b"",
            "headers": [(b"host", b"service.test"), (b"content-type", b"multipart/form-data; boundary=x"),
                        (b"content-length", b"10485760")],
            "client": ("203.0.113.9", 4000), "server": ("service.test", 80),
        }
        await main.app(scope, receive, send)
        self.assertEqual(received, [], "the upload must not be read before the key is checked")
        self.assertEqual(sent[0]["status"], 401)
        self.assertEqual(self.fake.calls, 0)

    async def test_keys_never_appear_in_logs(self):
        with mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != ENV_VAR}, clear=True):
            with self.assertLogs(level=logging.DEBUG) as captured:
                logging.getLogger("keyguard-test").debug("marker")
                await self.post(headers={"Authorization": f"Bearer {WRONG_KEY}"})
        with self.assertLogs(level=logging.DEBUG) as captured_wrong:
            logging.getLogger("keyguard-test").debug("marker")
            await self.post(headers={"Authorization": f"Bearer {WRONG_KEY}"})
        joined = "\n".join(captured.output + captured_wrong.output)
        for secret in (SERVICE_KEY, WRONG_KEY, OPENAI_CANARY):
            self.assertNotIn(secret, joined)
        self.assertIn("not configured", joined)

    def test_middleware_is_installed_on_the_app(self):
        self.assertIn(ServiceKeyMiddleware, [entry.cls for entry in main.app.user_middleware])


def main_model():
    from services.openai_service import DEFAULT_MODEL

    return DEFAULT_MODEL


if __name__ == "__main__":
    unittest.main()
