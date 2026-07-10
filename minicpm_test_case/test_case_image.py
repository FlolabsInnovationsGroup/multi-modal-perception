from openai import OpenAI
import base64
import json
import mimetypes
import os
import re
import time
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


# =========================
# API configuration
# =========================
# export MINICPM_API_KEY="你的_API_KEY"
#
# Windows PowerShell:
# $env:MINICPM_API_KEY="you_API_KEY" (I just use the official key)

minicpm_api_key = os.getenv("MINICPM_API_KEY", "lis_sk_298cf78155f231c7_DkrDcNLHnK8dJRnfFrJCd4JGDbBLMkHrC3T-wLpvC9zy0BPemsyFuQ")

client = OpenAI(
    api_key=minicpm_api_key,
    base_url="https://api.modelbest.co/v1",
)

MODEL_NAME = "MiniCPM-V-4.6-Instruct"


# =========================
# JSON / image utils
# =========================
def encode_image_to_base64(image_path: str) -> str:
    image_path_obj = Path(image_path)

    mime_type, _ = mimetypes.guess_type(str(image_path_obj))
    if mime_type is None:
        # 默认按 jpeg 处理
        mime_type = "image/jpeg"

    with open(image_path_obj, "rb") as file:
        image_base64 = base64.b64encode(file.read()).decode("utf-8")

    return f"data:{mime_type};base64,{image_base64}"


def extract_json_from_response(response_text: str) -> dict:
    response_text = response_text.strip()

    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON object from model response: {response_text}")


def save_json(data: Any, json_path: str) -> None:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# Latency utils
# =========================
def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    k = (len(values) - 1) * (p / 100)
    lower = int(k)
    upper = min(lower + 1, len(values) - 1)
    weight = k - lower

    return values[lower] * (1 - weight) + values[upper] * weight


# =========================
# GPU memory monitor
# =========================
def query_gpu_memory_mib(gpu_id: int = 0) -> Optional[float]:
    """
    Only useful when the model is actually running on your local GPU.

    If you use the official MiniCPM API, inference runs on the remote API server,
    so local GPU memory does not represent model memory usage.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_id}",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

        value = result.stdout.strip().splitlines()[0]
        return float(value)

    except Exception:
        return None


class GPUMemoryMonitor:
    def __init__(self, gpu_id: int = 0, interval_sec: float = 0.05):
        self.gpu_id = gpu_id
        self.interval_sec = interval_sec
        self.samples: List[float] = []
        self._stop_event = threading.Event()
        self._thread = None

    def _monitor(self):
        while not self._stop_event.is_set():
            memory = query_gpu_memory_mib(self.gpu_id)
            if memory is not None:
                self.samples.append(memory)
            time.sleep(self.interval_sec)

    def start(self):
        self.samples = []
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Optional[float]]:
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join()

        if not self.samples:
            return {
                "gpu_memory_min_mib": None,
                "gpu_memory_max_mib": None,
                "gpu_memory_mean_mib": None,
                "gpu_memory_num_samples": 0,
            }

        return {
            "gpu_memory_min_mib": min(self.samples),
            "gpu_memory_max_mib": max(self.samples),
            "gpu_memory_mean_mib": sum(self.samples) / len(self.samples),
            "gpu_memory_num_samples": len(self.samples),
        }


# =========================
# MiniCPM-o 4.5 API call
# =========================
def call_minicpm_o_45_api(
    client: OpenAI,
    model_name: str,
    prompt: str,
    image_data_url: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """
    Call official MiniCPM-o 4.5 Chat Completions API.

    The image is passed as a base64 data URL using image_url format.
    """

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url,
                        },
                    },
                ],
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content


# =========================
# Single inference with performance metrics
# =========================
def test_single_image_with_metrics(
    image_path: str,
    prompt_path: str,
    client: OpenAI,
    model_name: str,
    gpu_id: int = 0,
    monitor_gpu: bool = False,
) -> Dict[str, Any]:
    """
    Run one independent multimodal inference through MiniCPM-o 4.5 official API.

    Because official API inference runs remotely, monitor_gpu should normally be False.
    """
    image_path = Path(image_path)
    prompt_path = Path(prompt_path)

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read().strip()

    image = encode_image_to_base64(str(image_path))

    baseline_memory = query_gpu_memory_mib(gpu_id) if monitor_gpu else None

    gpu_monitor = GPUMemoryMonitor(gpu_id=gpu_id, interval_sec=0.05)

    if monitor_gpu:
        gpu_monitor.start()

    start_time = time.perf_counter()

    try:
        response_content = call_minicpm_o_45_api(
            client=client,
            model_name=model_name,
            prompt=prompt,
            image_data_url=image,
            temperature=0.0,
            max_tokens=2048,
        )
    finally:
        end_time = time.perf_counter()

        if monitor_gpu:
            gpu_stats = gpu_monitor.stop()
        else:
            gpu_stats = {
                "gpu_memory_min_mib": None,
                "gpu_memory_max_mib": None,
                "gpu_memory_mean_mib": None,
                "gpu_memory_num_samples": 0,
            }

    latency_sec = end_time - start_time

    model_result = extract_json_from_response(response_content)

    peak_memory = gpu_stats["gpu_memory_max_mib"]

    if baseline_memory is not None and peak_memory is not None:
        memory_delta = peak_memory - baseline_memory
    else:
        memory_delta = None

    result = {
        "id": image_path.stem,
        **model_result,
        "_raw_response": response_content,
        "_performance": {
            "latency_sec": latency_sec,
            "latency_ms": latency_sec * 1000,
            "gpu_id": gpu_id if monitor_gpu else None,
            "gpu_memory_note": (
                "GPU memory is not measured because inference runs on the official remote API."
                if not monitor_gpu
                else "GPU memory is measured on local machine only."
            ),
            "gpu_memory_baseline_mib": baseline_memory,
            "gpu_memory_peak_mib": peak_memory,
            "gpu_memory_delta_mib": memory_delta,
            "gpu_memory_min_mib": gpu_stats["gpu_memory_min_mib"],
            "gpu_memory_mean_mib": gpu_stats["gpu_memory_mean_mib"],
            "gpu_memory_num_samples": gpu_stats["gpu_memory_num_samples"],
        },
    }

    return result


# =========================
# Batch inference with P50 / P95
# =========================
def test_multiple_images_with_metrics(
    image_dir: str,
    prompt_dir: str,
    output_json_path: str,
    client: OpenAI,
    model_name: str,
    gpu_id: int = 0,
    monitor_gpu: bool = False,
) -> Dict[str, Any]:
    """
    Run multiple independent MiniCPM-o 4.5 API inferences and save:
      1. each model result
      2. per-image latency
      3. P50 / P95 latency
      4. optional local GPU memory usage

    For official API usage, monitor_gpu should normally be False.
    """
    image_dir = Path(image_dir)
    prompt_dir = Path(prompt_dir)

    image_paths = []
    for pattern in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
        image_paths.extend(image_dir.glob(pattern))

    image_paths = sorted(image_paths)

    results = []
    latency_values_sec = []
    gpu_peak_values = []
    gpu_delta_values = []

    missing_prompt_ids = []
    failed_ids = []

    for image_path in image_paths:
        prompt_path = prompt_dir / f"{image_path.stem}.txt"

        if not prompt_path.exists():
            print(f"[Warning] Prompt not found for image: {image_path.name}")
            missing_prompt_ids.append(image_path.stem)
            continue

        print(f"Testing image: {image_path.name}")

        try:
            result = test_single_image_with_metrics(
                image_path=str(image_path),
                prompt_path=str(prompt_path),
                client=client,
                model_name=model_name,
                gpu_id=gpu_id,
                monitor_gpu=monitor_gpu,
            )

            results.append(result)

            perf = result["_performance"]

            latency_values_sec.append(perf["latency_sec"])

            if perf["gpu_memory_peak_mib"] is not None:
                gpu_peak_values.append(perf["gpu_memory_peak_mib"])

            if perf["gpu_memory_delta_mib"] is not None:
                gpu_delta_values.append(perf["gpu_memory_delta_mib"])

        except Exception as e:
            print(f"[Error] Failed to test {image_path.name}: {e}")
            failed_ids.append(image_path.stem)

            results.append(
                {
                    "id": image_path.stem,
                    "error": str(e),
                }
            )

    summary = {
        "model": model_name,
        "api_base": "https://api.modelbest.co/v1",
        "num_images": len(image_paths),
        "num_success": len(latency_values_sec),
        "num_failed": len(failed_ids),
        "num_missing_prompt": len(missing_prompt_ids),

        "latency": {
            "mean_sec": sum(latency_values_sec) / len(latency_values_sec)
            if latency_values_sec else None,
            "p50_sec": percentile(latency_values_sec, 50),
            "p95_sec": percentile(latency_values_sec, 95),
            "min_sec": min(latency_values_sec) if latency_values_sec else None,
            "max_sec": max(latency_values_sec) if latency_values_sec else None,

            "mean_ms": (
                sum(latency_values_sec) / len(latency_values_sec) * 1000
                if latency_values_sec else None
            ),
            "p50_ms": (
                percentile(latency_values_sec, 50) * 1000
                if latency_values_sec else None
            ),
            "p95_ms": (
                percentile(latency_values_sec, 95) * 1000
                if latency_values_sec else None
            ),
        },

        "gpu_memory": {
            "enabled": monitor_gpu,
            "note": (
                "Official API inference runs remotely. Local GPU memory is not model memory."
                if not monitor_gpu
                else "Measured local GPU memory only."
            ),
            "gpu_id": gpu_id if monitor_gpu else None,
            "peak_memory_max_mib": max(gpu_peak_values)
            if gpu_peak_values else None,
            "peak_memory_mean_mib": sum(gpu_peak_values) / len(gpu_peak_values)
            if gpu_peak_values else None,
            "delta_memory_max_mib": max(gpu_delta_values)
            if gpu_delta_values else None,
            "delta_memory_mean_mib": sum(gpu_delta_values) / len(gpu_delta_values)
            if gpu_delta_values else None,
        },

        "failed_ids": failed_ids,
        "missing_prompt_ids": missing_prompt_ids,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    save_json(output, output_json_path)

    print(f"Saved results with performance metrics to: {output_json_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return output


# =========================
# Main
# =========================
if __name__ == "__main__":
    image_dir = "./data/ingredient/images"
    prompt_dir = "./data/ingredient/prompts"
    output_json_path = "./outputs/calorie_results_with_metrics.json"

    test_multiple_images_with_metrics(
        image_dir=image_dir,
        prompt_dir=prompt_dir,
        output_json_path=output_json_path,
        client=client,
        model_name=MODEL_NAME,
        gpu_id=0,
        monitor_gpu=False,
    )