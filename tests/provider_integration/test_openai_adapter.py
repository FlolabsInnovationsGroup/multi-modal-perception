import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.provider_integration.adapters.openai import (
    LocalGenerationResult,
    LocalTranscriptionResult,
    LocalValidationResult,
    OpenAIAdapter,
)


def _chat_response(content: str = "OK"):
    return SimpleNamespace(
        id="req_123",
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


def _transcription_response(text: str = "OK"):
    return SimpleNamespace(
        id="req_transcript_123",
        text=text,
        usage={"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
    )


def _status_error(status_code: int, code: str | None = None):
    exc = Exception("provider failure")
    exc.status_code = status_code
    exc.code = code
    return exc


class TestOpenAIAdapter(unittest.TestCase):
    def test_constructor_uses_fixed_base_url_and_zero_retries(self):
        seen = {}

        def factory(**kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())),
                audio=SimpleNamespace(transcriptions=SimpleNamespace(create=AsyncMock())),
            )

        adapter = OpenAIAdapter("test-provider-key-redacted", client_factory=factory)

        self.assertEqual(adapter.base_url, "https://api.openai.com/v1/")
        self.assertEqual(adapter.max_retries, 0)
        self.assertEqual(seen["api_key"], "test-provider-key-redacted")
        self.assertEqual(seen["base_url"], "https://api.openai.com/v1/")
        self.assertEqual(seen["max_retries"], 0)
        self.assertEqual(seen["timeout"], 30.0)

    def test_generate_text_success(self):
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=AsyncMock(return_value=_chat_response("OK")),
                )
            ),
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=AsyncMock())),
        )
        adapter = OpenAIAdapter("test-provider-key-redacted", client_factory=lambda **kwargs: fake_client)

        result = asyncio.run(adapter.generate_text(text="hello world"))

        self.assertIsInstance(result, LocalGenerationResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.result, "OK")
        self.assertEqual(result.model, "gpt-4o-mini")
        self.assertEqual(result.usage, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    def test_transcribe_audio_and_validation_success(self):
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())),
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(
                    create=AsyncMock(return_value=_transcription_response("OK")),
                )
            ),
        )
        adapter = OpenAIAdapter("test-provider-key-redacted", client_factory=lambda **kwargs: fake_client)

        transcript = asyncio.run(
            adapter.transcribe_audio(audio_bytes=b"\x00\x00\x00\x00", filename="probe.wav")
        )
        validation = asyncio.run(
            adapter.validate_access(
                context={"trusted": True},
                credential="test-provider-key-redacted",
                model="gpt-4o-mini-transcribe",
                operation="audio",
            )
        )

        self.assertIsInstance(transcript, LocalTranscriptionResult)
        self.assertIsInstance(validation, LocalValidationResult)
        self.assertTrue(transcript.ok)
        self.assertEqual(transcript.result, "OK")
        self.assertTrue(validation.ok)
        self.assertEqual(validation.status, "VALID")
        self.assertEqual(validation.model, "gpt-4o-mini-transcribe")

    def test_validate_access_maps_provider_statuses(self):
        cases = [
            (401, "invalid_api_key", "CREDENTIAL_REJECTED"),
            (401, "account_restricted", "ACCESS_DENIED"),
            (403, None, "CAPABILITY_DENIED"),
            (404, "model_not_found", "CAPABILITY_DENIED"),
            (429, "insufficient_quota", "QUOTA_EXCEEDED"),
            (429, "rate_limit_exceeded", "RATE_LIMITED"),
            (408, None, "PROVIDER_UNAVAILABLE"),
            (500, None, "PROVIDER_UNAVAILABLE"),
            (400, None, "INVALID_INPUT"),
            (418, None, "PROVIDER_RESPONSE_INVALID"),
        ]

        for status_code, code, expected in cases:
            fake_client = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(
                        create=AsyncMock(side_effect=_status_error(status_code, code)),
                    )
                ),
                audio=SimpleNamespace(
                    transcriptions=SimpleNamespace(create=AsyncMock()),
                ),
            )
            adapter = OpenAIAdapter(
                "test-provider-key-redacted",
                client_factory=lambda **kwargs: fake_client,
            )

            result = asyncio.run(
                adapter.validate_access(
                    context={"trusted": True},
                    credential="test-provider-key-redacted",
                    model="gpt-4o-mini",
                    operation="text",
                )
            )

            self.assertIsInstance(result, LocalValidationResult)
            self.assertEqual(result.status, expected, (status_code, code, expected, result.status))


if __name__ == "__main__":
    unittest.main()
