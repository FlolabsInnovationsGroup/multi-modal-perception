from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import logging
from typing import Optional
from schemas import PerceptionOutput
from services.openai_service import get_ultra_fast_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process", response_model=PerceptionOutput)
async def process_data(
    text_input: Optional[str] = Form(None),
    audio_file: UploadFile = File(...),
):
    """
    Main trigger for the perception system.
    """
    audio_bytes = await audio_file.read()

    try:
        normalized_text = (text_input or "").strip()
        if not normalized_text and audio_bytes:
            text_input = "reply to the audio"
        else:
            text_input = normalized_text

        ai_service = get_ultra_fast_service()
        processed_string = await ai_service.generate_multimodal_response(
            text_input=text_input,
            audio_bytes=audio_bytes,
            audio_filename=audio_file.filename or "audio.wav",
        )

        return PerceptionOutput(result=processed_string)

    except RuntimeError as config_error:
        raise HTTPException(
            status_code=500,
            detail="Perception system misconfiguration (missing OpenAI setup).",
        ) from config_error
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Perception System Error") from e
