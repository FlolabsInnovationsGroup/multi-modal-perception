#!/usr/bin/env python3
"""
Benchmark script that runs ON the GPU cloud machine (RunPod or Vast).
- Reports GPU name, memory, and a short compute benchmark (TFLOPS-style).
- Optionally runs a few training steps with a small model to simulate InternVL workload.
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
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
