import base64
import os
from typing import Optional

import httpx


MINICPM_API_URL = os.getenv("MINICPM_API_URL", "").rstrip("/")
MINICPM_MODEL = os.getenv("MINICPM_MODEL", "openbmb/MiniCPM-V-4.6")


class MiniCPMService:
    def __init__(self) -> None:
        self._base_url = MINICPM_API_URL

    async def generate_response(
        self,
        prompt: str,
        image_bytes: bytes = b"",
        image_content_type: str = "image/jpeg",
    ) -> tuple[str, str, int]:
        if not self._base_url:
            raise RuntimeError("MINICPM_API_URL is required for MiniCPM inference.")

        image = None
        if image_bytes:
            encoded_image = base64.b64encode(image_bytes).decode("ascii")
            image = f"data:{image_content_type};base64,{encoded_image}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/v1/generate",
                json={
                    "prompt": prompt,
                    "image": image,
                    "model": MINICPM_MODEL,
                },
            )
        response.raise_for_status()

        data = response.json()
        output = data.get("output")
        model = data.get("model")
        usage = data.get("usage")
        total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
        if not isinstance(output, str) or not isinstance(model, str):
            raise ValueError("MiniCPM service returned an invalid response.")

        return output.strip(), model, int(total_tokens)


_minicpm_service: Optional[MiniCPMService] = None


def get_minicpm_service() -> MiniCPMService:
    global _minicpm_service

    if _minicpm_service is None:
        _minicpm_service = MiniCPMService()

    return _minicpm_service
