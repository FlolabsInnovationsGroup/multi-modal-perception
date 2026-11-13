import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from api.process import process_data
from api.speech import transcribe_audio
from services.minicpm_service import MiniCPMService
from services.whisper_service import WhisperService


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeAsyncClient:
    def __init__(self, response_data):
        self.response_data = response_data
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, url, *, files=None, json=None):
        self.request = {"url": url, "files": files, "json": json}
        return FakeResponse(self.response_data)


class ModelServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_whisper_client_posts_uploaded_audio(self):
        client = FakeAsyncClient({"transcript": "  hello  ", "model": "small"})
        service = WhisperService()
        service._base_url = "http://gpu.test"

        with patch("services.whisper_service.httpx.AsyncClient", return_value=client):
            transcript, model = await service.transcribe_audio(b"wav-data", "speech.wav")

        self.assertEqual((transcript, model), ("hello", "small"))
        self.assertEqual(client.request["url"], "http://gpu.test/v1/transcribe")
        self.assertEqual(
            client.request["files"]["audio_file"],
            ("speech.wav", b"wav-data", "application/octet-stream"),
        )

    async def test_minicpm_client_posts_prompt_and_image(self):
        client = FakeAsyncClient(
            {
                "output": "  A red car.  ",
                "model": "openbmb/MiniCPM-V-4.6",
                "usage": {"total_tokens": 23},
            }
        )
        service = MiniCPMService()
        service._base_url = "http://gpu.test"

        with patch("services.minicpm_service.httpx.AsyncClient", return_value=client):
            result = await service.generate_response(
                "Describe it",
                image_bytes=b"image-data",
                image_content_type="image/jpeg",
            )

        self.assertEqual(result, ("A red car.", "openbmb/MiniCPM-V-4.6", 23))
        self.assertEqual(client.request["url"], "http://gpu.test/v1/generate")
        self.assertEqual(client.request["json"]["prompt"], "Describe it")
        self.assertTrue(client.request["json"]["image"].startswith("data:image/jpeg;base64,"))

    async def test_process_transcribes_audio_and_routes_image_to_minicpm(self):
        whisper = AsyncMock()
        whisper.transcribe_audio.return_value = ("turn left", "small")
        minicpm = AsyncMock()
        minicpm.generate_response.return_value = ("The image shows a road.", "MiniCPM-V-4.6", 19)
        audio_file = UploadFile(
            file=io.BytesIO(b"audio-data"),
            filename="speech.wav",
            headers=Headers({"content-type": "audio/wav"}),
        )
        image_file = UploadFile(
            file=io.BytesIO(b"image-data"),
            filename="road.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        with (
            patch("api.process.get_whisper_service", return_value=whisper),
            patch("api.process.get_minicpm_service", return_value=minicpm),
        ):
            result = await process_data("What is here?", audio_file, image_file)

        self.assertEqual(result.result, "The image shows a road.")
        self.assertEqual(result.model, "MiniCPM-V-4.6")
        self.assertEqual(result.file_type, "image")
        self.assertEqual(
            minicpm.generate_response.call_args.kwargs["prompt"],
            "What is here?\n\nAudio transcript:\nturn left",
        )
        self.assertEqual(
            minicpm.generate_response.call_args.kwargs["image_bytes"],
            b"image-data",
        )

    async def test_process_rejects_empty_request(self):
        with self.assertRaises(HTTPException) as error:
            await process_data(None, None, None)

        self.assertEqual(error.exception.status_code, 422)

    async def test_transcribe_endpoint_returns_model_and_transcript(self):
        whisper = AsyncMock()
        whisper.transcribe_audio.return_value = ("hello", "small")
        audio_file = UploadFile(file=io.BytesIO(b"audio-data"), filename="speech.wav")

        with patch("api.speech.get_whisper_service", return_value=whisper):
            result = await transcribe_audio(audio_file)

        self.assertEqual(result.transcript, "hello")
        self.assertEqual(result.model, "small")


if __name__ == "__main__":
    unittest.main()
