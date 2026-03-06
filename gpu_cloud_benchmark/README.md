# GPU Cloud Benchmark: RunPod vs Vast.ai for InternVL 38B

This folder contains code and infrastructure to **test and compare RunPod and Vast.ai** using a fixed budget (e.g. **$5 per provider**) so you can see which is **faster and better** for training **InternVL 38B**.

## What it does

1. **RunPod**: Creates an on-demand A100 80GB pod, runs a GPU benchmark script over SSH, then terminates.
2. **Vast.ai**: Launches an A100 instance, runs the same benchmark, then destroys it.
3. **Comparison**: Prints startup time, total time, estimated cost, GPU name, compute throughput (GFLOPS), and **InternVL3-38B** inference/training metrics. Results are also saved to `comparison_results.json`.

The in-cloud benchmark loads **OpenGVLab/InternVL3-38B-hf** from Hugging Face on the GPU machine, runs inference (text-only, multiple generations) to report **tokens/sec**, and optionally runs a few training steps to measure step time. It also runs a matrix-multiply compute benchmark.

**To ensure the benchmark uses InternVL3-38B:** By default, before running the benchmark the orchestrator **installs** `transformers`, `accelerate`, and `bitsandbytes` on the cloud machine via SSH (`pip install`). So you don’t need a custom image — just run `python run_comparison.py` and the model will be used. Set `GPU_BENCHMARK_INSTALL_DEPS=0` if your image already has these deps (to save ~2–5 min per provider).

## Requirements

- **API keys**
  - [RunPod](https://www.runpod.io/console/user/settings): create an API key and set `RUNPOD_API_KEY`.
  - [Vast.ai](https://cloud.vast.ai/account/): create an API key and set `VAST_API_KEY`.
- **SSH access**: Add your **public SSH key** to both RunPod and Vast.ai so the runner can copy and execute the benchmark script on the machine.
  - RunPod: [SSH keys](https://docs.runpod.io/pods/configuration/use-ssh).
  - Vast: your profile / SSH key settings.
- **Local**: Python 3.10+, `requests`. No GPU required on your laptop. Dependencies are in the **project root** `requirements.txt`; use the **root** `.venv`.
- **Cloud machine**: The default image has PyTorch + CUDA. The orchestrator **automatically installs** `transformers`, `accelerate`, and `bitsandbytes` on the machine before running the benchmark, so InternVL3-38B is used without a custom image.

## Setup

From the **project root** (one `requirements.txt`, one `.venv`):

```bash
# From repo root
cd /path/to/multi-modal-perception
python -m pip install -r requirements.txt
source .venv/bin/activate   # or on Windows: .venv\Scripts\activate

cd gpu_cloud_benchmark
export RUNPOD_API_KEY="your-runpod-key"
export VAST_API_KEY="your-vast-key"
# Optional: if your SSH key is not ~/.ssh/id_ed25519 or ~/.ssh/id_rsa
export SSH_KEY_PATH="$HOME/.ssh/id_ed25519"
# Optional: change budget (default $5 per provider)
export GPU_BENCHMARK_BUDGET=5.0
```

## Verify setup (no credits used)

Before spending any credits, check that API keys and SSH are working:

```bash
# If "python run_comparison.py --check" shows NO output, your venv's python may be broken (ENOEXEC).
# Use one of these instead:
./run_check.sh
# or
python3 run_comparison.py --check
# or
python run_comparison.py --check
```

`run_check.sh` uses `python3` from your PATH so you always see output. This validates RunPod API, Vast.ai API, and local SSH key **without creating any pods or instances**. Fix any failures before running the full benchmark. **Logging:** the script also writes `run_comparison_started.txt`, `run_comparison.log`, and `check_setup_result.txt` in this folder.

## Run the comparison

```bash
python run_comparison.py
```

**What you'll see before any credits are used:**

1. **Price per hour** for RunPod and Vast (for the GPUs used).
2. **Credit usage & time (estimate):** estimated total time (~25–45 min), estimated cost per provider and total, and per-provider caps ($5 default).
3. **Confirmation:** *Use credits and start benchmark? [y/N]* — answer `y` only when you're ready to create machines and spend credits.
4. **Per-provider (optional):** After each machine is ready, *Start benchmark on RunPod/Vast now? [y/N]* — you can skip that provider (machine is then terminated immediately) or run the benchmark.

To skip all prompts (e.g. in scripts or CI), set `AUTO_CONFIRM=1` or pass `--yes`:

```bash
AUTO_CONFIRM=1 python run_comparison.py
# or
python run_comparison.py --yes
```

This will:

1. Create a RunPod A100 80GB pod, wait until SSH is ready, run the benchmark, then terminate the pod.
2. Create a Vast.ai A100 instance, wait until SSH is ready, run the benchmark, then destroy the instance.
3. Print a comparison (startup time, total time, estimated cost, GPU name, throughput) and write `comparison_results.json`.

With ~$5 per provider you get roughly 2–3 hours of A100 80GB time; the script only uses a few minutes per run, so you stay well under budget.

## InternVL 38B note

- **InternVL 38B** needs ~150GB+ GPU memory for full training (vision + 32B LLM). Typical setups use **2× A100 80GB** or a single 80GB with heavy quantization/LoRA.
- This benchmark uses **1× A100 80GB** to compare **raw GPU performance and provider speed/cost** (startup, throughput). For actual InternVL 38B training you would:
  - Use `gpu_count=2` (or multi-GPU in config) and a training script that loads InternVL and runs on your dataset (e.g. from `caipo_multimodal_dataset`).

## Files

| File | Purpose |
|------|--------|
| `config.py` | Budget, GPU types, image, timeouts. |
| `runpod_client.py` | RunPod REST API: create pod, wait, get SSH, terminate. |
| `vast_client.py` | Vast.ai REST API: search offers, create instance, wait, get SSH, destroy. |
| `run_benchmark_on_machine.py` | Script that runs **on** the GPU machine: GPU info, InternVL3-38B inference/training benchmark, and matrix-multiply compute benchmark. |
| `requirements-benchmark.txt` | Python deps for the cloud machine (transformers, accelerate, etc.) when running the InternVL benchmark. |
| `run_remote.py` | Copies the benchmark script via SCP and runs it over SSH. |
| `run_comparison.py` | Orchestrator: RunPod benchmark → Vast benchmark → print comparison, save JSON. |

## Optional: run only one provider

- RunPod only: set `VAST_API_KEY=` (empty) or comment out the Vast section in `run_comparison.py`.
- Vast only: set `RUNPOD_API_KEY=` (empty) or comment out the RunPod section.

## Optional: adjust GPU or image

Edit `config.py`:

- `RUNPOD_GPU_TYPE_IDS`: e.g. `["NVIDIA A100 80GB PCIe"]`.
- `VAST_GPU_NAME`: e.g. `"A100"`.
- `RUNPOD_IMAGE` / `VAST_IMAGE`: Docker image with PyTorch + CUDA (default RunPod PyTorch image). For InternVL benchmark, use an image that has `pip install -r gpu_cloud_benchmark/requirements-benchmark.txt` (or equivalent).

## Optional: InternVL benchmark env (on the cloud machine)

The script reads these when running on the GPU machine (you can pass them via `run_remote` or the image’s default env):

- `INTERNVL_MODEL_ID`: Hugging Face model id (default `OpenGVLab/InternVL3-38B-hf`).
- `BENCHMARK_INTERNVL`: Set to `0` to skip loading InternVL and only run the matrix-multiply benchmark.
- `INTERNVL_NUM_INFERENCE_RUNS`: Number of generate() runs for inference throughput (default `5`).
- `INTERNVL_MAX_NEW_TOKENS`: Max new tokens per generation (default `50`).
- `INTERNVL_NUM_TRAINING_STEPS`: Number of training steps to run (default `0`). Use 1–2 with 4-bit to test training; set `INTERNVL_4BIT=1` if needed.
- `INTERNVL_4BIT`: Set to `1` to load the model in 4-bit (needs `bitsandbytes`); useful for training benchmark or low VRAM.
