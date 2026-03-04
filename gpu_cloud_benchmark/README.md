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
- **Local**: Python 3.10+, `requests`. No GPU required on your laptop.

## Setup

```bash
cd gpu_cloud_benchmark
pip install -r requirements.txt
export RUNPOD_API_KEY="your-runpod-key"
export VAST_API_KEY="your-vast-key"
# Optional: if your SSH key is not ~/.ssh/id_ed25519 or ~/.ssh/id_rsa
export SSH_KEY_PATH="$HOME/.ssh/id_ed25519"
# Optional: change budget (default $5 per provider)
export GPU_BENCHMARK_BUDGET=5.0
```

## Run the comparison

```bash
python run_comparison.py
```

**Confirmations (optional):**

1. **Before starting:** The script shows current price/hr for RunPod and Vast (for the GPUs you will use) and asks: *Proceed with benchmark? [y/N]*. Answer `y` to continue, or `n` to exit without creating any machines.
2. **Before each test:** After a machine is ready (e.g. RunPod pod is up with SSH), the script asks: *Start benchmark on RunPod now? [y/N]*. You can skip that provider’s benchmark (the machine is then terminated immediately) or run it.

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
