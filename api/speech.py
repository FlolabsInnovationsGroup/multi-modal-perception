import logging
import wave

from fastapi import APIRouter, HTTPException, Request, Response
from openai import APIError, BadRequestError

from schemas import SynthesisInput, TranscriptionOutput
from services.openai_service import get_ultra_fast_service

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 25_000_000
AUDIO_EXTENSIONS = {
    "": "wav",
    "application/octet-stream": "wav",
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
    "audio/webm": "webm",
    "video/mp4": "mp4",
    "video/webm": "webm",
}


@router.post(
    "/transcribe",
    response_model=TranscriptionOutput,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in AUDIO_EXTENSIONS
                if media_type
            },
        }
    },
)
async def transcribe(request: Request) -> TranscriptionOutput:
    """Transcribe a recording sent as raw file bytes."""
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    extension = AUDIO_EXTENSIONS.get(media_type)
    if extension is None:
        raise HTTPException(415, "Unsupported audio content type.")

    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio must be 25 MB or smaller.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(422, "Provide audio bytes in the request body.")

    try:
        service = get_ultra_fast_service()
        text = await service.transcribe_audio(bytes(audio), f"audio.{extension}")
    except BadRequestError as exc:
        if exc.param == "model" or exc.code == "model_not_found":
            raise HTTPException(502, "Speech transcription failed.") from exc
        raise HTTPException(422, "The audio could not be transcribed.") from exc
    except APIError as exc:
        logger.warning("Speech transcription failed: %s", type(exc).__name__)
        raise HTTPException(502, "Speech transcription failed.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "Speech service configuration error.") from exc
    return TranscriptionOutput(text=text)


@router.post(
    "/synthesize",
    response_class=Response,
    responses={
        200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def synthesize(payload: SynthesisInput) -> Response:
    """Synthesize text as 16 kHz mono 16-bit PCM WAV."""
    try:
        service = get_ultra_fast_service()
    except RuntimeError as exc:
        raise HTTPException(500, "Speech service configuration error.") from exc

    try:
        audio = await service.synthesize_speech(payload.text)
    except (APIError, ValueError, EOFError, wave.Error) as exc:
        logger.warning("Speech synthesis failed: %s", type(exc).__name__)
        raise HTTPException(502, "Speech synthesis failed.") from exc
    return Response(content=audio, media_type="audio/wav")
