import base64
import io
import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
import requests
import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor
import uvicorn


# =====================================================================
# 1. Automatic .env Loader (Zero-dependency)
# =====================================================================
def load_env_file(filepath: str = ".env"):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    os.environ[k] = v
        print(f"[Config] Loaded environment variables from {filepath}")


load_env_file()

app = FastAPI(title="Multimodal Inference Server")

IDLE_TIMEOUT_SECONDS = 10  # 5 minutes


# =====================================================================
# 2. Inactivity Watchdog (Uses MACHINE_ID & JL_API_KEY from .env)
# =====================================================================
class PostRequestWatchdog:

    def __init__(self, timeout_seconds: int = IDLE_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self.is_active = False

    def start_or_reset(self):
        """Starts/resets the 5-minute inactivity countdown."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self.is_active = True
            self._timer = threading.Timer(
                self.timeout_seconds, self._trigger_pause
            )
            self._timer.daemon = True
            self._timer.start()
            print(
                f"\n[Watchdog] ⏱️ Inactivity timer active: will pause instance in {self.timeout_seconds}s if no new requests arrive."
            )

    def _trigger_pause(self):
        print(
            f"\n[Watchdog] ⏰ Inactivity timeout reached! Pausing instance..."
        )

        machine_id = os.getenv("MACHINE_ID", "471345")
        print(
            f"[Watchdog] Executing: jl pause {machine_id} --yes --json ..."
        )

        try:
            # Pass environment with JL_API_KEY to subprocess
            env = os.environ.copy()
            pause_res = subprocess.run(
                ["jl", "pause", str(machine_id), "--yes", "--json"],
                capture_output=True,
                text=True,
                env=env,
            )

            if pause_res.returncode == 0:
                print(
                    f"[Watchdog] ✅ Instance {machine_id} pause command accepted by JarvisLabs!"
                )
                if pause_res.stdout.strip():
                    print(f"[Watchdog] Output: {pause_res.stdout.strip()}")
            else:
                print(
                    f"[Watchdog] ❌ Pause failed (code {pause_res.returncode}):"
                )
                print(f"Stdout: {pause_res.stdout.strip()}")
                print(f"Stderr: {pause_res.stderr.strip()}")

        except Exception as e:
            print(f"[Watchdog ERROR] Failed to run jl pause: {e}")


# Initialize watchdog (idle until the first POST request)
watchdog = PostRequestWatchdog(timeout_seconds=IDLE_TIMEOUT_SECONDS)


# =====================================================================
# 3. Model Initialization
# =====================================================================
MODEL_ID = os.getenv("MODEL_ID", "openbmb/MiniCPM-V-4.6")
print(f"\nLoading {MODEL_ID} on GPU...")

processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    dtype=torch.bfloat16,
    trust_remote_code=True,
).eval()

print("Model loaded successfully. Ready for requests.\n")


class GenerateRequest(BaseModel):
    prompt: str
    image: Optional[str] = None
    model: Optional[str] = MODEL_ID
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7


def parse_image_input(image_str: str) -> Image.Image:
    if image_str.startswith(("http://", "https://")):
        resp = requests.get(image_str, timeout=15)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    elif image_str.startswith("data:image") or len(image_str) > 100:
        if "," in image_str:
            image_str = image_str.split(",", 1)[1]
        img_bytes = base64.b64decode(image_str)
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")
    raise ValueError("Unrecognized image format")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID}


@app.post("/v1/generate")
def generate_endpoint(req: GenerateRequest):
    try:
        if req.image:
            pil_img = parse_image_input(req.image)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": pil_img},
                        {"type": "text", "text": req.prompt},
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": req.prompt}]

        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)

        prompt_tokens = int(inputs["input_ids"].shape[-1])

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=req.max_tokens,
                do_sample=(req.temperature > 0),
                temperature=req.temperature if req.temperature > 0 else None,
            )

        generated_tokens = outputs[0][prompt_tokens:]
        output_text = processor.decode(
            generated_tokens, skip_special_tokens=True
        )

        completion_tokens = int(len(generated_tokens))
        total_tokens = prompt_tokens + completion_tokens

        # Start or reset the 5-minute countdown
        watchdog.start_or_reset()

        return {
            "output": output_text,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "model": req.model or MODEL_ID,
        }

    except Exception as e:
        watchdog.start_or_reset()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6007)