from fastapi import APIRouter, UploadFile, Form, HTTPException, File
from typing import Optional
from schemas import PerceptionInput, PerceptionOutput
from services.qwen_service import get_qwen_service
router = APIRouter()


@router.post("/process_qwen", response_model=PerceptionOutput)
async def process_qwen(
    text_input: str = Form(...),
    image_file: Optional[UploadFile] = File(None),
    audio_file: Optional[UploadFile] = File(None),
):
    image_url = None
    if image_file:
        # image_url = await upload_to_storage(image_file)
        pass

    audio_url = None
    if audio_file:
        # audio_url = await upload_to_storage(audio_file)
        pass

    try:
        qwen_service = get_qwen_service()
        qwen_response = await qwen_service.generate_response(
            text=text_input,
            image_url=image_url,
            audio_url=audio_url,
        )
        return PerceptionOutput(result=qwen_response)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Qwen API error: {str(exc)}",
        ) from exc