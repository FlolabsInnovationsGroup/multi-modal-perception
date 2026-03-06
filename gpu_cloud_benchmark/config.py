"""
Configuration for GPU cloud benchmark (RunPod vs Vast.ai) for InternVL 38B training.
"""
import os
from pathlib import Path

# Hard limit: $5 per provider (override with GPU_BENCHMARK_BUDGET env if needed)
BUDGET_PER_PROVIDER_USD = float(os.getenv("GPU_BENCHMARK_BUDGET", "5.0"))
BUDGET_LIMIT_USD = 5.0  # Enforced cap; total spend per provider will not exceed this

# GPU preference: A100 80GB is required for InternVL 38B (multi-GPU or large single GPU)
# For ~$5 you get ~2–3 hours on A100 80GB (RunPod ~$1.19–1.59/hr, Vast ~$1.50–3/hr)
RUNPOD_GPU_TYPE_IDS = ["NVIDIA A100 80GB PCIe", "NVIDIA A100-SXM4-80GB"]
VAST_GPU_NAME = "A100"  # Vast.ai search by name

# Container image with PyTorch + CUDA for training
RUNPOD_IMAGE = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04"
VAST_IMAGE = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04"

# Disk (GB). InternVL 38B + dataset needs space; 100GB container is a safe default.
CONTAINER_DISK_GB = 100

# Timeouts
POD_STARTUP_TIMEOUT_SEC = 600  # 10 min max wait for pod/instance to be ready
BENCHMARK_TIMEOUT_SEC = 3600   # 1 hour max for benchmark script

# Paths (benchmark script runs inside cloud; we copy it or run inline)
REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_SCRIPT_NAME = "run_benchmark_on_machine.py"

# Install transformers/accelerate on the cloud machine before running the benchmark?
# Set to False if your image already has them (saves ~2–5 min per provider).
INSTALL_BENCHMARK_DEPS = os.getenv("GPU_BENCHMARK_INSTALL_DEPS", "1").strip().lower() in ("1", "true", "yes")

# Model to use for the GPU benchmark (Hugging Face model id).
INTERNVL_MODEL_ID = os.getenv("INTERNVL_MODEL_ID", "OpenGVLab/InternVL3-38B-hf")
