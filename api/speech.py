import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from schemas import TranscriptionOutput
from services.whisper_service import get_whisper_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/transcribe", response_model=TranscriptionOutput)
async def transcribe_audio(audio_file: UploadFile = File(...)):
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="audio_file must not be empty.")

    try:
        transcript, model = await get_whisper_service().transcribe_audio(
            audio_bytes,
            audio_file.filename or "audio.wav",
        )
        return TranscriptionOutput(transcript=transcript, model=model)
    except RuntimeError as config_error:
        raise HTTPException(
            status_code=500,
            detail="Whisper service is not configured.",
        ) from config_error
    except Exception as error:
        logger.exception("Audio transcription failed")
        raise HTTPException(status_code=502, detail="Audio transcription failed.") from error
