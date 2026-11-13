from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import logging
from typing import Optional
from schemas import PerceptionOutput
from services.minicpm_service import get_minicpm_service
from services.whisper_service import get_whisper_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process", response_model=PerceptionOutput)
async def process_data(
    text_input: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
):
    """
    Main trigger for the perception system.
    """
    if audio_file is not None:
        audio_bytes = await audio_file.read()
        audio_filename = audio_file.filename or "audio.wav"
    else:
        audio_bytes = b""
        audio_filename = "audio.wav"

    if image_file is not None:
        image_bytes = await image_file.read()
        image_content_type = image_file.content_type or "image/jpeg"
        if image_bytes and not image_content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="image_file must be an image.")
    else:
        image_bytes = b""
        image_content_type = "image/jpeg"

    normalized_text = (text_input or "").strip()
    if not normalized_text and not audio_bytes and not image_bytes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one of text_input, audio_file, or image_file.",
        )

    try:
        prompt_parts = [normalized_text] if normalized_text else []
        if audio_bytes:
            transcript, _ = await get_whisper_service().transcribe_audio(
                audio_bytes,
                audio_filename,
            )
            if transcript:
                prompt_parts.append(f"Audio transcript:\n{transcript}")
        if not prompt_parts:
            prompt_parts.append("Describe the image." if image_bytes else "Respond to the audio.")

        minicpm_service = get_minicpm_service()
        processed_string, model, _ = await minicpm_service.generate_response(
            prompt="\n\n".join(prompt_parts),
            image_bytes=image_bytes,
            image_content_type=image_content_type,
        )

        file_type = "image" if image_bytes else "audio" if audio_bytes else "text"

        return PerceptionOutput(
            result=processed_string,
            model=model,
            file_type=file_type,
        )

    except RuntimeError as config_error:
        raise HTTPException(
            status_code=500,
            detail="Perception model service misconfiguration.",
        ) from config_error
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Perception System Error") from e