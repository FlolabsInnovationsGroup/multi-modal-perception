from fastapi import APIRouter, HTTPException
import logging
from schemas import PerceptionInput, PerceptionOutput
from services.openai_service import get_ultra_fast_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process", response_model=PerceptionOutput)
async def process_data(payload: PerceptionInput):
    """
    Main trigger for the perception system.
    """
    logger.info(f"Received input: {payload.text_input}")

    try:
        ai_service = get_ultra_fast_service()
        processed_string = await ai_service.generate_response(payload.text_input)

        logger.info("Processing complete.")
        return PerceptionOutput(result=processed_string)

    except RuntimeError as config_error:
        raise HTTPException(
            status_code=500,
            detail="Perception system misconfiguration (missing OpenAI setup).",
        ) from config_error
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Perception System Error") from e
