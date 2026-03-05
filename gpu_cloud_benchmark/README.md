# GPU Cloud Benchmark: RunPod vs Vast.ai for InternVL 38B

This folder contains code and infrastructure to **test and compare RunPod and Vast.ai** using a fixed budget (e.g. **$5 per provider**) so you can see which is **faster and better** for training **InternVL 38B**.

## What it does

1. **RunPod**: Creates an on-demand A100 80GB pod, runs a GPU benchmark script over SSH, then terminates.
2. **Vast.ai**: Launches an A100 instance, runs the same benchmark, then destroys it.
3. **Comparison**: Prints startup time, total time, estimated cost, GPU name, and compute throughput (GFLOPS). Results are also saved to `comparison_results.json`.

The in-cloud benchmark reports GPU info and a short matrix-multiply throughput; it does **not** download or train the full InternVL 38B (that would use most of your $5 on download time). You can extend `run_benchmark_on_machine.py` to add a few training steps with a small model or LoRA if you want a more realistic training benchmark.

## Requirements

- **API keys**
  - [RunPod](https://www.runpod.io/console/user/settings): create an API key and set `RUNPOD_API_KEY`.
  - [Vast.ai](https://cloud.vast.ai/account/): create an API key and set `VAST_API_KEY`.
- **SSH access**: Add your **public SSH key** to both RunPod and Vast.ai so the runner can copy and execute the benchmark script on the machine.
  - RunPod: [SSH keys](https://docs.runpod.io/pods/configuration/use-ssh).
  - Vast: your profile / SSH key settings.
- **Local**: Python 3.10+, `requests`. No GPU required on your laptop. Dependencies are in the **project root** `requirements.txt`; use the **root** `.venv`.

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
| `run_benchmark_on_machine.py` | Script that runs **on** the GPU machine: GPU info + compute benchmark. |
| `run_remote.py` | Copies the benchmark script via SCP and runs it over SSH. |
| `run_comparison.py` | Orchestrator: RunPod benchmark → Vast benchmark → print comparison, save JSON. |

## Optional: run only one provider

- RunPod only: set `VAST_API_KEY=` (empty) or comment out the Vast section in `run_comparison.py`.
- Vast only: set `RUNPOD_API_KEY=` (empty) or comment out the RunPod section.

## Optional: adjust GPU or image

Edit `config.py`:

- `RUNPOD_GPU_TYPE_IDS`: e.g. `["NVIDIA A100 80GB PCIe"]`.
- `VAST_GPU_NAME`: e.g. `"A100"`.
- `RUNPOD_IMAGE` / `VAST_IMAGE`: Docker image with PyTorch + CUDA (default RunPod PyTorch image).
