import os
import io
import json
import base64
import time
import threading
import subprocess
from typing import Optional, Dict, Any, List

import requests
import torch

from PIL import Image

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import uvicorn

from transformers import (
    AutoProcessor,
    AutoModelForImageTextToText,
)

# ============================================================
# Config
# ============================================================

MODEL_ID = os.getenv(
    "MODEL_ID",
    "openbmb/MiniCPM-V-4.6"
)

PORT = 6007

app = FastAPI(
    title="MiniCPM-V-4.6 Multimodal Server"
)

# ============================================================
# Watchdog
# ============================================================

IDLE_TIMEOUT_SECONDS = 600


class Watchdog:

    def __init__(self):
        self.timer = None
        self.lock = threading.Lock()

    def reset(self):

        with self.lock:
            if self.timer:
                self.timer.cancel()

            self.timer = threading.Timer(
                IDLE_TIMEOUT_SECONDS,
                self.pause
            )

            self.timer.daemon = True
            self.timer.start()

    def pause(self):

        machine_id = os.getenv("MACHINE_ID")

        if not machine_id:
            return

        try:
            subprocess.run(
                [
                    "jl",
                    "pause",
                    str(machine_id),
                    "--yes"
                ]
            )

        except Exception:
            pass


watchdog = Watchdog()

# ============================================================
# Load Model
# ============================================================


print("=" * 70)
print("Loading MiniCPM-V-4.6")
print("=" * 70)

processor = AutoProcessor.from_pretrained(
    MODEL_ID,
    trust_remote_code=True
)

# ------------------------------------------------------------
# IMPORTANT FIX
# MiniCPM-V-4.6 default 16x causes vision reshape error
# ------------------------------------------------------------

processor.image_processor.downsample_mode = "4x"

print(
    "Image processor:",
    processor.image_processor
)

model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID,
    device_map="auto",
    dtype=torch.bfloat16,
    trust_remote_code=True
).eval()

print("Model loaded")
print(
    "GPU:",
    torch.cuda.get_device_name(0)
    if torch.cuda.is_available()
    else "CPU"
)


# ============================================================
# Request Models
# ============================================================


class GenerateRequest(BaseModel):
    prompt: str

    image: Optional[str] = None

    model: Optional[str] = MODEL_ID

    max_tokens: int = 2048

    temperature: float = 0.7


class ImageTextBatchRequest(BaseModel):
    image_dir: str

    prompt_dir: str

    output_json_path: str


# ============================================================
# Image loader
# ============================================================


def parse_image_input(
        image_str: str
):
    if image_str.startswith(
            ("http://", "https://")
    ):
        r = requests.get(
            image_str,
            timeout=30
        )

        r.raise_for_status()

        return Image.open(
            io.BytesIO(r.content)
        ).convert("RGB")

    if image_str.startswith(
            "data:image"
    ):
        image_str = image_str.split(
            ",",
            1
        )[1]

    data = base64.b64decode(
        image_str
    )

    return Image.open(
        io.BytesIO(data)
    ).convert("RGB")


# ============================================================
# Core inference
# ============================================================


def run_single(
        image: Image.Image,
        prompt: str,
        max_tokens: int = 2048,
):
    messages = [
        {
            "role": "user",
            "content":
                [
                    {
                        "type": "image",
                        "image": image
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt"
    )

    print("========== DEBUG ==========")

    print("image size:", image.size)

    print(
        "processor downsample:",
        processor.image_processor.downsample_mode
    )

    print(
        "input keys:",
        inputs.keys()
    )

    if "pixel_values" in inputs:
        print(
            "pixel_values:",
            inputs["pixel_values"].shape
        )

    if "target_sizes" in inputs:
        print(
            "target_sizes:",
            inputs["target_sizes"]
        )

    print(
        "pixel batch:",
        inputs["pixel_values"].shape[0]
    )

    print(
        "target batch:",
        inputs["target_sizes"].shape[0]
    )

    print("==========================")

    inputs = inputs.to(
        model.device
    )

    prompt_tokens = (
        inputs["input_ids"]
        .shape[-1]
    )

    with torch.no_grad():

        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            downsample_mode="4x",
        )

    generated = outputs[0][
                prompt_tokens:
                ]

    text = processor.decode(
        generated,
        skip_special_tokens=True
    )

    return text


# ============================================================
# Health
# ============================================================


@app.get("/health")
def health():
    return {

        "status": "ok",

        "model": MODEL_ID,

        "model_loaded": True,

        "cuda_available":
            torch.cuda.is_available(),

        "gpu":
            torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else None,

        "downsample_mode":
            processor.image_processor.downsample_mode
    }


# ============================================================
# Single generate
# ============================================================


@app.post("/v1/generate")
def generate(
        req: GenerateRequest
):
    try:

        if req.image:

            image = parse_image_input(
                req.image
            )

            output = run_single(
                image,
                req.prompt
            )

        else:

            raise ValueError(
                "image required"
            )

        watchdog.reset()

        return {

            "output": output,

            "model": MODEL_ID

        }


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# Batch test
# ============================================================


@app.post("/v1/test/image-text")
def test_image_text(
        req: ImageTextBatchRequest
):
    start = time.time()

    images = sorted(
        [
            x for x in os.listdir(
            req.image_dir
        )
            if x.lower().endswith(
            (".jpg", ".jpeg", ".png")
        )
        ]
    )

    results = []

    success = 0
    failed = 0

    for idx, name in enumerate(images):

        item_id = os.path.splitext(
            name
        )[0]

        print(
            f"[{idx + 1}/{len(images)}]",
            item_id
        )

        try:

            image_path = os.path.join(
                req.image_dir,
                name
            )

            prompt_path = os.path.join(
                req.prompt_dir,
                item_id + ".txt"
            )

            image = Image.open(
                image_path
            ).convert(
                "RGB"
            )

            with open(
                    prompt_path,
                    encoding="utf-8"
            ) as f:

                prompt = f.read().strip()

            output = run_single(
                image,
                prompt
            )

            results.append({

                "id": item_id,

                "image": name,

                "success": True,

                "output": output

            })

            success += 1



        except Exception as e:

            failed += 1

            results.append({

                "id": item_id,

                "image": name,

                "success": False,

                "error": str(e)

            })

    data = {

        "model": MODEL_ID,

        "summary": {

            "num_images": len(images),

            "num_success": success,

            "num_failed": failed,

            "total_test_time_sec":
                time.time() - start,

            "downsample_mode":
                processor.image_processor.downsample_mode

        },

        "results": results

    }

    os.makedirs(
        os.path.dirname(
            req.output_json_path
        ),
        exist_ok=True
    )

    with open(
            req.output_json_path,
            "w",
            encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    watchdog.reset()

    return data


# ============================================================
# Main
# ============================================================


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT
    )