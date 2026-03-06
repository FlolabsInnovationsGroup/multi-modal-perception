#!/usr/bin/env python3
"""
Benchmark script that runs ON the GPU cloud machine (RunPod or Vast).
- Reports GPU name, memory.
- Loads OpenGVLab/InternVL3-38B from Hugging Face and runs inference + optional
  training steps to test GPU capabilities for this model.
- Falls back to matrix-multiply compute benchmark if InternVL is skipped (e.g. missing deps).
Output is JSON lines to stdout so the orchestrator can parse metrics.
"""
import json
import os
import sys
import time

# Optional: PyTorch for real GPU benchmark
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# Optional: Transformers for InternVL3-38B
INTERNVL_MODEL_ID = os.getenv("INTERNVL_MODEL_ID", "OpenGVLab/InternVL3-38B-hf")
BENCHMARK_INTERNVL = os.getenv("BENCHMARK_INTERNVL", "1").strip().lower() in ("1", "true", "yes")
HAS_INTERNVL = False
if BENCHMARK_INTERNVL and HAS_TORCH:
    try:
        from transformers import AutoProcessor, AutoModelForImageTextToText
        HAS_INTERNVL = True
    except ImportError:
        pass
try:
    from transformers import BitsAndBytesConfig
    HAS_BITSANDBYTES = True
except ImportError:
    HAS_BITSANDBYTES = False


def gpu_info() -> dict:
    """Collect GPU name and memory (no PyTorch required if nvidia-smi exists)."""
    info = {"gpu_name": None, "gpu_memory_gb": None, "cuda_available": False}
    if HAS_TORCH and torch.cuda.is_available():
        info["cuda_available"] = True
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["gpu_memory_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)
        info["gpu_count"] = torch.cuda.device_count()
    else:
        # Fallback: nvidia-smi
        import subprocess
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                timeout=10,
            )
            parts = out.strip().split("\n")[0].split(",")
            if len(parts) >= 2:
                info["gpu_name"] = parts[0].strip()
                info["gpu_memory_gb"] = float(parts[1].strip().replace(" MiB", "").strip()) / 1024
            info["gpu_count"] = out.strip().count("\n") + 1
        except Exception as e:
            info["error"] = str(e)
    return info


def run_internvl_benchmark(
    model_id: str,
    num_inference_runs: int = 5,
    max_new_tokens: int = 50,
    num_training_steps: int = 0,
) -> dict:
    """
    Load InternVL3-38B and run inference (and optionally a few training steps).
    Returns dict with tokens_per_sec, inference_sec, training_step_sec (if run), error (if any).
    """
    out = {
        "model_id": model_id,
        "internvl_tokens_per_sec": None,
        "internvl_inference_sec": None,
        "internvl_training_step_sec": None,
        "internvl_loaded_dtype": None,
        "internvl_quantization": None,
    }
    if not HAS_TORCH or not torch.cuda.is_available():
        out["error"] = "PyTorch/CUDA not available"
        return out
    if not HAS_INTERNVL:
        out["error"] = "transformers not installed (pip install transformers>=4.37.2 accelerate)"
        return out

    device = "cuda"
    torch_dtype = torch.bfloat16
    quantization_config = None
    # 38B bf16 ~76GB; use 4-bit if we have bitsandbytes and want to be safe or run training
    use_4bit = num_training_steps > 0 or os.getenv("INTERNVL_4BIT", "").strip().lower() in ("1", "true", "yes")
    if use_4bit and HAS_BITSANDBYTES:
        quantization_config = BitsAndBytesConfig(load_in_4bit=True)
        out["internvl_quantization"] = "4bit"

    try:
        # Load processor and model
        load_start = time.perf_counter()
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        if quantization_config is not None:
            model = AutoModelForImageTextToText.from_pretrained(
                model_id,
                quantization_config=quantization_config,
                device_map=device,
                trust_remote_code=True,
            )
            out["internvl_loaded_dtype"] = "4bit"
        else:
            model = AutoModelForImageTextToText.from_pretrained(
                model_id,
                device_map=device,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            )
            out["internvl_loaded_dtype"] = "bfloat16"
        model.eval()
        load_sec = time.perf_counter() - load_start
        out["internvl_load_sec"] = round(load_sec, 2)

        # Device for inputs (device_map models may not have .device)
        try:
            dev = next(model.parameters()).device
        except StopIteration:
            dev = torch.device(device)
        inp_dtype = torch_dtype if quantization_config is None else torch.float16

        # ---- Inference benchmark (text-only to avoid image download) ----
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Write a haiku."}]}
        ]
        total_new_tokens = 0
        inf_start = time.perf_counter()
        for _ in range(num_inference_runs):
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            if hasattr(inputs, "to"):
                inputs = inputs.to(dev, dtype=inp_dtype)
            else:
                def to_dev(x):
                    if not hasattr(x, "to"):
                        return x
                    try:
                        return x.to(dev, dtype=inp_dtype)
                    except (TypeError, AttributeError):
                        return x.to(dev)
                inputs = {k: to_dev(v) for k, v in inputs.items()}
            with torch.no_grad():
                gen_ids = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            # Count new tokens (excluding input)
            input_len = inputs["input_ids"].shape[1]
            total_new_tokens += (gen_ids.shape[1] - input_len)
        inf_elapsed = time.perf_counter() - inf_start
        out["internvl_inference_sec"] = round(inf_elapsed, 2)
        out["internvl_tokens_per_sec"] = round(total_new_tokens / inf_elapsed, 2) if inf_elapsed > 0 else 0
        out["internvl_total_tokens"] = total_new_tokens

        # ---- Optional: a few training steps (4-bit recommended) ----
        if num_training_steps > 0:
            model.train()
            # Reuse same prompt; create labels (shifted input_ids for causal LM loss)
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            if hasattr(inputs, "to"):
                inputs = inputs.to(dev)
            else:
                inputs = {k: v.to(dev) if hasattr(v, "to") else v for k, v in inputs.items()}
            input_ids = inputs["input_ids"]
            labels = input_ids.clone()
            labels[:, :-1] = input_ids[:, 1:].clone()
            labels[:, -1] = -100  # ignore last token for loss
            step_times = []
            for _ in range(num_training_steps):
                if hasattr(model, "zero_grad"):
                    model.zero_grad()
                torch.cuda.synchronize()
                t0 = time.perf_counter()
                outputs = model(input_ids=input_ids, labels=labels)
                loss = outputs.loss
                loss.backward()
                torch.cuda.synchronize()
                step_times.append(time.perf_counter() - t0)
            out["internvl_training_step_sec"] = round(sum(step_times) / len(step_times), 2) if step_times else None
            model.eval()

    except Exception as e:
        out["error"] = str(e)
    return out


def run_compute_benchmark(secs: float = 10.0) -> dict:
    """Run a short GPU compute benchmark (matrix multiply). Returns throughput (GFLOPS) and time."""
    if not HAS_TORCH or not torch.cuda.is_available():
        return {"error": "PyTorch/CUDA not available", "throughput_gflops": 0}
    device = torch.device("cuda:0")
    # Large matmul to stress GPU
    n = 8192
    a = torch.randn(n, n, dtype=torch.float32, device=device)
    b = torch.randn(n, n, dtype=torch.float32, device=device)
    torch.cuda.synchronize()
    start = time.perf_counter()
    steps = 0
    end_time = start + secs
    while time.perf_counter() < end_time:
        c = torch.matmul(a, b)
        torch.cuda.synchronize()
        steps += 1
    elapsed = time.perf_counter() - start
    # 2*n^3 flops per matmul
    flops_per_step = 2 * (n ** 3)
    total_flops = flops_per_step * steps
    gflops = total_flops / elapsed / 1e9
    return {
        "elapsed_sec": round(elapsed, 2),
        "steps": steps,
        "throughput_gflops": round(gflops, 2),
        "matrix_size": n,
    }


def main():
    results = {"provider": os.getenv("BENCHMARK_PROVIDER", "unknown"), "gpu": gpu_info()}
    print(json.dumps({"event": "gpu_info", **results}), flush=True)

    if results["gpu"].get("error"):
        print(json.dumps({"event": "error", "message": results["gpu"]["error"]}), flush=True)
        sys.exit(1)

    # InternVL3-38B benchmark (if enabled and deps available)
    internvl_result = {}
    if BENCHMARK_INTERNVL:
        num_inference = int(os.getenv("INTERNVL_NUM_INFERENCE_RUNS", "5"))
        max_tokens = int(os.getenv("INTERNVL_MAX_NEW_TOKENS", "50"))
        num_train_steps = int(os.getenv("INTERNVL_NUM_TRAINING_STEPS", "0"))
        internvl_result = run_internvl_benchmark(
            model_id=INTERNVL_MODEL_ID,
            num_inference_runs=num_inference,
            max_new_tokens=max_tokens,
            num_training_steps=num_train_steps,
        )
        print(json.dumps({"event": "internvl_benchmark", **internvl_result}), flush=True)
        if internvl_result.get("error"):
            print(json.dumps({"event": "internvl_skip", "reason": internvl_result["error"]}), flush=True)

    # Fallback/supplement: matrix multiply benchmark
    bench_secs = float(os.getenv("BENCHMARK_COMPUTE_SEC", "10"))
    compute = run_compute_benchmark(secs=bench_secs)
    results["compute"] = compute
    print(json.dumps({"event": "compute_benchmark", **compute}), flush=True)

    # Final summary line for easy parsing
    summary = {
        "event": "summary",
        "provider": results["provider"],
        "gpu_name": results["gpu"].get("gpu_name"),
        "gpu_memory_gb": results["gpu"].get("gpu_memory_gb"),
        "throughput_gflops": compute.get("throughput_gflops"),
        "compute_elapsed_sec": compute.get("elapsed_sec"),
    }
    if internvl_result.get("internvl_tokens_per_sec") is not None:
        summary["internvl_tokens_per_sec"] = internvl_result["internvl_tokens_per_sec"]
        summary["internvl_inference_sec"] = internvl_result.get("internvl_inference_sec")
        summary["internvl_training_step_sec"] = internvl_result.get("internvl_training_step_sec")
        summary["internvl_model"] = INTERNVL_MODEL_ID
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
