from openai import OpenAI
import base64
import json
import re
import time
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


# =========================
# API configuration
# =========================
openai_api_key = "token-abc123"
openai_api_base = "http://localhost:8000/v1"

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)

MODEL_NAME = "<model_path>"


# =========================
# JSON / image / audio utils
# =========================
def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as file:
        image_base64 = base64.b64encode(file.read()).decode("utf-8")

    return "data:image/jpeg;base64," + image_base64


def encode_audio_to_base64(audio_path: str) -> str:
    with open(audio_path, "rb") as file:
        audio_base64 = base64.b64encode(file.read()).decode("utf-8")

    return "data:audio/mpeg;base64," + audio_base64


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
    """
    Compute percentile without numpy.

    Args:
        values: list of numbers
        p: percentile, for example 50 or 95
    """
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
    Query current GPU memory usage by nvidia-smi.

    Returns:
        memory used in MiB.
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
    """
    Poll GPU memory during inference.

    This measures total GPU memory usage on one GPU.
    If other processes are using the same GPU, they will be included.
    """

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
# Single inference with performance metrics
# =========================
def test_single_image_with_metrics(
    image_path: str,
    audio_path: str,
    client: OpenAI,
    model_name: str,
    gpu_id: int = 0,
    monitor_gpu: bool = True,
) -> Dict[str, Any]:
    """
    Run one independent image-and-audio inference.

    Returns:
        {
          "id": "calorie_000001",
          ...model returned fields...,
          "_raw_response": "...",
          "_performance": {
            "latency_sec": 1.234,
            "gpu_memory_baseline_mib": 12345,
            "gpu_memory_peak_mib": 13000,
            "gpu_memory_delta_mib": 655
          }
        }
    """
    image_path = Path(image_path)
    audio_path = Path(audio_path)

    image = encode_image_to_base64(str(image_path))
    audio = encode_audio_to_base64(str(audio_path))

    baseline_memory = query_gpu_memory_mib(gpu_id) if monitor_gpu else None

    gpu_monitor = GPUMemoryMonitor(gpu_id=gpu_id, interval_sec=0.05)

    if monitor_gpu:
        gpu_monitor.start()

    start_time = time.perf_counter()

    try:
        chat_response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image,
                            },
                        },
                        {
                            "type": "audio_url",
                            "audio_url": {
                                "url": audio,
                            },
                        },
                    ],
                }
            ],
            extra_body={
                "stop_token_ids": [151643, 151645]
            },
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

    response_content = chat_response.choices[0].message.content
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
            "gpu_id": gpu_id,
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
    audio_dir: str,
    output_json_path: str,
    client: OpenAI,
    model_name: str,
    gpu_id: int = 0,
    monitor_gpu: bool = True,
) -> Dict[str, Any]:
    """
    Run multiple independent inferences and save:
      1. each model result
      2. per-image latency
      3. P50 / P95 latency
      4. per-image GPU memory usage
      5. overall GPU memory statistics
    """
    image_dir = Path(image_dir)
    audio_dir = Path(audio_dir)

    image_paths = sorted(image_dir.glob("*.jpg"))

    results = []
    latency_values_sec = []
    gpu_peak_values = []
    gpu_delta_values = []

    missing_audio_ids = []
    failed_ids = []

    for image_path in image_paths:
        audio_path = audio_dir / f"{image_path.stem}.mp3"

        print(f"Testing image: {image_path.name}")

        try:
            result = test_single_image_with_metrics(
                image_path=str(image_path),
                audio_path=str(audio_path),
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
        "num_images": len(image_paths),
        "num_success": len(latency_values_sec),
        "num_failed": len(failed_ids),
        "num_missing_audio": len(missing_audio_ids),

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
            "gpu_id": gpu_id,
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
        "missing_audio_ids": missing_audio_ids,
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
    image_dir = r".\data\food_calories\images"
    audio_dir = r".\data\food_calories\audio_prompts"
    output_json_path = "./outputs/calorie_results_with_metrics.json"

    test_multiple_images_with_metrics(
        image_dir=image_dir,
        audio_dir=audio_dir,
        output_json_path=output_json_path,
        client=client,
        model_name=MODEL_NAME,
        gpu_id=0,
        monitor_gpu=True,
    )