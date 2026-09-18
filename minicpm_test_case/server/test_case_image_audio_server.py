import os
import io
import json
import time
import base64
import threading
import subprocess

from typing import Optional

import requests
import torch

from PIL import Image

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import uvicorn


from faster_whisper import WhisperModel


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


WHISPER_MODEL = os.getenv(
    "WHISPER_MODEL",
    "small"
)


PORT = 6007


app = FastAPI(
    title="MiniCPM-V-4.6 Image Audio Server"
)



# ============================================================
# Watchdog
# ============================================================


IDLE_TIMEOUT_SECONDS = 600


class Watchdog:


    def __init__(self):

        self.timer=None
        self.lock=threading.Lock()



    def reset(self):

        with self.lock:

            if self.timer:
                self.timer.cancel()


            self.timer=threading.Timer(
                IDLE_TIMEOUT_SECONDS,
                self.pause
            )

            self.timer.daemon=True

            self.timer.start()



    def pause(self):

        machine_id=os.getenv(
            "MACHINE_ID"
        )


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



watchdog=Watchdog()



# ============================================================
# Load Whisper
# ============================================================


print("="*70)
print("Loading Whisper")
print("="*70)


whisper_model = WhisperModel(
    WHISPER_MODEL,
    device="cuda",
    compute_type="float16"
)


print(
    "Whisper loaded:",
    WHISPER_MODEL
)



# ============================================================
# Load MiniCPM
# ============================================================


print("="*70)
print("Loading MiniCPM-V-4.6")
print("="*70)



processor = AutoProcessor.from_pretrained(
    MODEL_ID,
    trust_remote_code=True
)



# critical fix
processor.image_processor.downsample_mode="4x"



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



print("MiniCPM loaded")



print(
    "GPU:",
    torch.cuda.get_device_name(0)
    if torch.cuda.is_available()
    else "CPU"
)




# ============================================================
# Request Models
# ============================================================


class GenerateAudioRequest(BaseModel):

    image:str

    audio:str

    prompt:Optional[str]=(
        "Estimate calories. Return only JSON."
    )



class ImageAudioBatchRequest(BaseModel):

    image_dir:str

    audio_dir:str

    output_json_path:str



# ============================================================
# Image loader
# ============================================================


def load_image(path_or_url):


    if path_or_url.startswith(
        ("http://","https://")
    ):


        r=requests.get(
            path_or_url,
            timeout=30
        )

        r.raise_for_status()


        return Image.open(
            io.BytesIO(r.content)
        ).convert("RGB")



    return Image.open(
        path_or_url
    ).convert("RGB")





# ============================================================
# Audio loader
# ============================================================


def transcribe_audio(
    audio_path
):


    segments, info = whisper_model.transcribe(
        audio_path
    )


    texts=[]


    for seg in segments:

        texts.append(
            seg.text
        )


    transcript=" ".join(texts).strip()


    return transcript





# ============================================================
# MiniCPM inference
# ============================================================


def run_minicpm(
    image,
    prompt
):


    messages=[

        {

            "role":"user",

            "content":[

                {
                    "type":"image",
                    "image":image
                },

                {
                    "type":"text",
                    "text":prompt
                }

            ]

        }

    ]



    inputs=processor.apply_chat_template(

        messages,

        add_generation_prompt=True,

        tokenize=True,

        return_dict=True,

        return_tensors="pt"

    )



    print("========== DEBUG ==========")

    print(
        "image:",
        image.size
    )


    print(
        "downsample:",
        processor.image_processor.downsample_mode
    )


    print(
        "pixel_values:",
        inputs["pixel_values"].shape
    )


    print(
        "target_sizes:",
        inputs["target_sizes"]
    )


    print("==========================")



    inputs=inputs.to(
        model.device
    )



    prompt_tokens=(
        inputs["input_ids"]
        .shape[-1]
    )



    with torch.no_grad():

        outputs=model.generate(

            **inputs,

            max_new_tokens=2048,

            downsample_mode="4x"

        )



    generated=outputs[0][
        prompt_tokens:
    ]



    result=processor.decode(

        generated,

        skip_special_tokens=True

    )



    return result





# ============================================================
# Full image audio pipeline
# ============================================================


def run_image_audio(
    image_path,
    audio_path,
    extra_prompt=""
):


    transcript=transcribe_audio(
        audio_path
    )



    prompt=f"""
Audio transcript:

{transcript}


{extra_prompt}


Return only JSON.
""".strip()



    image=load_image(
        image_path
    )



    answer=run_minicpm(
        image,
        prompt
    )



    return {

        "transcript":transcript,

        "answer":answer

    }





# ============================================================
# Health
# ============================================================


@app.get("/health")
def health():


    return {


        "status":"ok",

        "model":MODEL_ID,

        "whisper":WHISPER_MODEL,

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
# Single audio inference
# ============================================================


@app.post("/v1/generate-audio")
def generate_audio(
    req:GenerateAudioRequest
):


    try:


        result=run_image_audio(

            req.image,

            req.audio,

            req.prompt

        )



        watchdog.reset()



        return {


            "model":MODEL_ID,

            **result

        }



    except Exception as e:


        raise HTTPException(

            status_code=500,

            detail=str(e)

        )





# ============================================================
# Batch test
# ============================================================


@app.post("/v1/test/image-audio")
def test_image_audio(
    req:ImageAudioBatchRequest
):


    start=time.time()



    audio_files=sorted(

        [

            x for x in os.listdir(
                req.audio_dir
            )

            if x.lower().endswith(
                (
                    ".wav",
                    ".mp3",
                    ".m4a"
                )
            )

        ]

    )



    results=[]


    success=0

    failed=0



    for idx,audio_name in enumerate(audio_files):


        item_id=os.path.splitext(
            audio_name
        )[0]



        print(
            f"[{idx+1}/{len(audio_files)}]",
            item_id
        )



        try:


            audio_path=os.path.join(
                req.audio_dir,
                audio_name
            )



            image_path=os.path.join(

                req.image_dir,

                item_id+".jpg"

            )



            result=run_image_audio(

                image_path,

                audio_path

            )



            results.append({

                "id":item_id,

                "audio":audio_name,

                "success":True,

                **result

            })


            success+=1




        except Exception as e:


            failed+=1


            results.append({

                "id":item_id,

                "audio":audio_name,

                "success":False,

                "error":str(e)

            })





    output={


        "model":MODEL_ID,


        "summary":{

            "num_audio":

                len(audio_files),


            "num_success":

                success,


            "num_failed":

                failed,


            "total_time_sec":

                time.time()-start

        },


        "results":results

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

            output,

            f,

            indent=2,

            ensure_ascii=False

        )



    watchdog.reset()



    return output





# ============================================================
# Main
# ============================================================


if __name__=="__main__":


    uvicorn.run(

        app,

        host="0.0.0.0",

        port=PORT

    )