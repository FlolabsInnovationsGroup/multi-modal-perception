import os
from openai import OpenAI
from fastapi import HTTPException


DEFAULT_MODEL = os.getenv("QWEN_MODEL", "qwen3-omni-flash")
MAX_TOKENS = int(os.getenv("QWEN_MAX_TOKENS", "1024"))
TEMPERATURE = float(os.getenv("QWEN_TEMPERATURE", "0.7"))


SYSTEM_PROMPT = os.getenv(
    "QWEN_SYSTEM_PROMPT",
    (
        "You are a fast, concise multimodal perception assistant. "
        "Given text input that may describe visual, audio, or sensor context, "
        "return a short, actionable analysis focused on what matters operationally."
    ),
)


class UltraFastQwenService:
    def __init__(self) -> None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY environment variable is required for Qwen integration."
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )


    async def generate_response(
        self,
        text: str,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> str:
        """
        Generate a text response from Qwen given text + optional image + optional audio.
        """
        content = [{"type": "text", "text": text}]

        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        if audio_url:
            content.append({"type": "audio_url", "audio_url": {"url": audio_url}})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

        try:
            response = await self._client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
            return (response.choices[0].message.content or "").strip()

        except Exception as exc:
            return f"Qwen temporarily unavailable. Echoing input: {text}"

        except Exception as exc:  # optional: more fine‑grained error handling
            raise HTTPException(
                status_code=500,
                detail=f"Qwen API error: {str(exc)}",
            ) from exc


# Singleton instance (like get_ultra_fast_service)
_qwen_service: UltraFastQwenService | None = None


def get_qwen_service() -> UltraFastQwenService:
    """
    Lazily-initialized singleton for Qwen client.
    """
    global _qwen_service

    if _qwen_service is None:
        _qwen_service = UltraFastQwenService()

    return _qwen_service