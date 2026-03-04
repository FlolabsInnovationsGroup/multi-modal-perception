from fastapi import APIRouter, HTTPException
from schemas import PerceptionInput, PerceptionOutput
from services.openai_service import get_ultra_fast_service

router = APIRouter()


@router.post("/process", response_model=PerceptionOutput)
async def process_data(payload: PerceptionInput):
    """
    Main trigger for the perception system.
    """

    try:
        ai_service = get_ultra_fast_service()
        processed_string = await ai_service.generate_response(payload.text_input)

        return PerceptionOutput(result=processed_string)

    except RuntimeError as config_error:
        raise HTTPException(
            status_code=500,
            detail="Perception system misconfiguration (missing OpenAI setup).",
        ) from config_error
    except Exception as e:  
        raise HTTPException(status_code=500, detail="Internal Perception System Error") from e
