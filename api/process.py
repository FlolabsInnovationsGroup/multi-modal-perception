from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from schemas import PerceptionInput, PerceptionOutput

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/process", response_model=PerceptionOutput)
async def process_data(payload: PerceptionInput):
    """
    The main trigger for the perception system.
    """
    logger.info(f"Received input: {payload.text_input}")
    
    try:

        processed_string = f"Hello world {payload.text_input}"

        
        logger.info("Processing complete.")
        return PerceptionOutput(result=processed_string)
        
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Perception System Error")