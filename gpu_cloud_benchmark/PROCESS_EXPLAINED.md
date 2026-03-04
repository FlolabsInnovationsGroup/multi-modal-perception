# Step-by-step: what each file and piece of code does

This document walks through the **exact process** of the GPU cloud benchmark: what runs where, what each function does, and how the pieces connect.

---

## 1. You run one command

```bash
python run_comparison.py
```

Everything else is triggered from this script. It uses the **config**, talks to **RunPod** and **Vast** via the **clients**, uses **run_remote** to run a script on each cloud machine, and that script is **run_benchmark_on_machine.py**.

---

## 2. `config.py` — central settings

**Role:** Single place for budget, GPU types, images, timeouts, and paths. No API calls; just variables other modules import.

| Variable | What it does |
|----------|---------------|
| `BUDGET_PER_PROVIDER_USD` | Max budget per provider (default 5.0). Can override with env `GPU_BENCHMARK_BUDGET`. |
| `BUDGET_LIMIT_USD` | Hard cap $5; reported cost and benchmark timeout are capped so we never exceed this. |
| `RUNPOD_GPU_TYPE_IDS` | List of GPU types to request from RunPod (e.g. A100 80GB PCIe, A100 SXM). RunPod picks one that’s available. |
| `VAST_GPU_NAME` | GPU name used when searching Vast.ai offers (e.g. `"A100"`). |
| `RUNPOD_IMAGE` / `VAST_IMAGE` | Docker image run on the machine (PyTorch + CUDA). Same image on both for a fair comparison. |
| `CONTAINER_DISK_GB` | Disk size (GB) for the container (e.g. 100). |
| `POD_STARTUP_TIMEOUT_SEC` | How long to wait for a pod/instance to become “running” with SSH (e.g. 600 s). |
| `BENCHMARK_TIMEOUT_SEC` | Max time allowed for the benchmark script on the remote machine (e.g. 3600 s). |
| `REPO_ROOT`, `BENCHMARK_SCRIPT_NAME` | Paths used to find the benchmark script. |

So: **config = “how much to spend, which GPU, which image, how long to wait.”**

---

## 3. `run_comparison.py` — main flow (orchestrator)

**Role:** Run RunPod benchmark, then Vast benchmark, then print and save a comparison. Runs **on your laptop** (no GPU needed).

### 3.1 `main()`

1. **Budget**  
   Uses `min(BUDGET_LIMIT_USD, BUDGET_PER_PROVIDER_USD)` so the effective cap is always at most $5. Prints: `Budget limit: $5.0 per provider`.

2. **SSH key**  
   Looks for `SSH_KEY_PATH`, or `~/.ssh/id_ed25519`, or `~/.ssh/id_rsa`. That key must be added to RunPod and Vast so the script can SCP/SSH into the machines.

3. **Run RunPod**  
   If `RUNPOD_API_KEY` is set, calls `run_runpod_benchmark(ssh_key, budget)`.

4. **Run Vast**  
   If `VAST_API_KEY` is set, calls `run_vast_benchmark(ssh_key, budget)`.

5. **Print comparison**  
   For each provider: startup time, total time, estimated cost (capped at $5), GPU name, memory, throughput (GFLOPS).

6. **Save**  
   Writes all results to `comparison_results.json`.

So: **main = “prepare env → run RunPod → run Vast → compare and save.”**

### 3.2 `run_runpod_benchmark(ssh_key_path, budget_usd)`

Step-by-step:

1. **Create pod**  
   Calls `runpod_client.create_pod(...)` with name, image, GPU types, disk, etc. RunPod API returns a pod object; we keep `pod_id`.

2. **Wait until usable**  
   Calls `runpod_wait(pod_id)` (i.e. `runpod_client.wait_until_running`). It polls `GET /pods/{id}` until status is RUNNING and we have `publicIp` and SSH port (e.g. `portMappings["22"]`). Measures `startup_sec`.

3. **Get SSH connection**  
   `get_ssh_info(pod)` returns `(host, port)` (e.g. public IP and mapped port 22).

4. **Budget cap for benchmark**  
   `cost_per_hr = 1.39` (typical RunPod A100).  
   `max_bench_sec = min(900, (BUDGET_LIMIT_USD / cost_per_hr) * 3600)` so the remote benchmark is never allowed to run longer than the $5 limit allows.

5. **Run benchmark on the pod**  
   Calls `run_script_ssh(host, port, ..., env={"BENCHMARK_PROVIDER": "runpod"}, timeout=max_bench_sec)`. That copies `run_benchmark_on_machine.py` to the pod and runs it over SSH. We get back `(returncode, stdout, stderr)`.

6. **Parse output**  
   `parse_benchmark_output(stdout)` reads JSON lines from the benchmark script; the line with `"event": "summary"` gives GPU name, memory, throughput, etc.

7. **Cost**  
   `elapsed = total time since create`.  
   `estimated_cost = min(BUDGET_LIMIT_USD, (elapsed / 3600) * cost_per_hr)` so reported cost never exceeds $5.

8. **Cleanup (always)**  
   In a `finally` block, calls `terminate_pod(pod_id)` so the pod is deleted even if something fails.

So: **run_runpod_benchmark = “create → wait → SSH → run benchmark (under $5 cap) → parse → terminate.”**

### 3.3 `run_vast_benchmark(ssh_key_path, budget_usd)`

Same idea as RunPod, but for Vast:

1. **Launch and wait**  
   `launch_and_wait(...)` (from `vast_client`) searches for the cheapest A100 offer, creates an instance from that offer, then polls until it’s running and has SSH info. Returns `(instance_id, inst)`.

2. **SSH**  
   `vast_get_ssh_info(inst)` gives `(host, port)`.

3. **Budget cap**  
   Uses the instance’s price: `dph = inst.get("dph_total") or ...` (dollars per hour).  
   `max_bench_sec = min(900, (BUDGET_LIMIT_USD / cost_per_hr) * 3600)`.

4. **Run benchmark**  
   `run_script_ssh(..., env={"BENCHMARK_PROVIDER": "vast"}, timeout=max_bench_sec)`.

5. **Parse and cost**  
   Same as RunPod: parse stdout for summary, compute `estimated_cost = min(BUDGET_LIMIT_USD, ...)`.

6. **Cleanup**  
   In `finally`, `destroy_instance(instance_id)`.

So: **run_vast_benchmark = “launch instance → wait → SSH → run benchmark (under $5) → parse → destroy.”**

### 3.4 `parse_benchmark_output(stdout)`

- Reads the remote script’s stdout line by line.
- Each line is expected to be JSON (e.g. `{"event": "gpu_info", ...}`, `{"event": "compute_benchmark", ...}`, `{"event": "summary", ...}`).
- When it finds a line with `"event": "summary"`, it returns that object (GPU name, memory, throughput, etc.). So the orchestrator only needs the final summary line to build the comparison table.

---

## 4. `runpod_client.py` — RunPod API

**Role:** Talk to RunPod’s REST API: create a pod, poll until it’s running with SSH, get SSH (host, port), terminate. All from your laptop.

| Function | What it does |
|----------|---------------|
| `_headers()` | Builds request headers: `Content-Type: application/json` and `Authorization: Bearer <RUNPOD_API_KEY>`. Fails if `RUNPOD_API_KEY` is not set. |
| `create_pod(...)` | `POST https://rest.runpod.io/v1/pods` with JSON: name, imageName, gpuTypeIds, gpuCount, containerDiskInGb, cloudType, ports `"22/tcp"`, supportPublicIp `true`. Returns the pod object (includes `id`). |
| `get_pod(pod_id)` | `GET .../pods/{pod_id}`. Returns current pod state (status, publicIp, portMappings, etc.). |
| `list_pods()` | `GET .../pods`. Returns list of your pods (e.g. for debugging). |
| `terminate_pod(pod_id)` | `DELETE .../pods/{pod_id}`. Stops billing and removes the pod. |
| `wait_until_running(pod_id, timeout_sec, poll_interval)` | Loop: every `poll_interval` seconds, call `get_pod(pod_id)`. If status is RUNNING and we have `publicIp` and a port mapping for 22, return the pod. Otherwise keep waiting until `timeout_sec`. Raises `TimeoutError` if never ready. |
| `get_ssh_info(pod)` | From the pod dict, reads `publicIp` and `portMappings["22"]` (or equivalent). Returns `(host, port)` for SSH. Raises if missing. |

So: **runpod_client = “create pod, wait until SSH is available, get SSH (host, port), terminate.”**

---

## 5. `vast_client.py` — Vast.ai API

**Role:** Search for GPU offers, create an instance from the cheapest offer, wait until running with SSH, get (host, port), destroy. All from your laptop.

| Function | What it does |
|----------|---------------|
| `_headers()` | Same idea as RunPod: `Authorization: Bearer <VAST_API_KEY>`. |
| `search_offers(gpu_name, num_gpus, min_gpu_ram)` | `PUT https://console.vast.ai/api/v0/search/asks/` with a query: verified, num_gpus, rentable, cuda_max_good, optional gpu_name and gpu_ram. Order by `dph_total` ascending (cheapest first). Returns list of offers; each has an `id` (ask id). |
| `create_instance(offer_id, image, disk_gb, label, runtype)` | `PUT .../asks/{offer_id}/` with image, disk, label, runtype `"ssh"`, target_state `"running"`. This “accepts” the offer and creates your instance. Response has `new_contract` (instance id). Returns that id. |
| `list_instances()` | `GET .../instances/`. List of your instances. |
| `get_instance(instance_id)` | `GET .../instances/{id}/`. Returns instance dict; unwraps if API returns `{ "instance": {...} }`. |
| `destroy_instance(instance_id)` | `DELETE .../instances/{id}/`. Stops billing and removes the instance. |
| `wait_until_running(instance_id, ...)` | Loop: poll `get_instance(instance_id)`. When status is `"running"` and `get_ssh_info(inst)` returns non-None, return the instance. Otherwise wait up to `timeout_sec`. |
| `get_ssh_info(inst)` | Tries several possible field names from Vast’s API (public_ip, host, connection.host, ssh_port, port_mapping["22"], etc.). Returns `(host, port)` or `None` if not ready. |
| `launch_and_wait(...)` | One-shot: `search_offers` → take first (cheapest) offer → `create_instance` with that offer’s id → `wait_until_running`. Returns `(instance_id, instance_dict)`. |

So: **vast_client = “find cheapest A100 offer → create instance → wait for SSH → get (host, port), and later destroy.”**

---

## 6. `run_remote.py` — run a script on the cloud machine via SSH

**Role:** Copy the benchmark script onto the remote host and execute it. Runs on your laptop; the script runs on the GPU machine.

| Step | What it does |
|------|---------------|
| **SCP** | Runs `scp -o StrictHostKeyChecking=no -o ConnectTimeout=30 -P {port} [-i key] {script_path} root@{host}:/tmp/run_benchmark_on_machine.py`. So the file that runs on the cloud is your local `run_benchmark_on_machine.py`. If SCP fails, returns that exit code and stderr. |
| **SSH + run** | Runs `ssh ... root@{host} "cd /tmp && BENCHMARK_PROVIDER="runpod" python3 /tmp/run_benchmark_on_machine.py"` (with the env vars you passed). Captures stdout and stderr, respects `timeout`. Returns `(returncode, stdout, stderr)`. |

So: **run_remote = “copy script to /tmp on the machine, then SSH in and run it with the given env and timeout.”** The orchestrator uses this for both RunPod and Vast, with different `BENCHMARK_PROVIDER` and timeout derived from the $5 limit.

---

## 7. `run_benchmark_on_machine.py` — runs on the GPU machine

**Role:** Run only on the cloud (RunPod or Vast). Detects GPU, runs a short compute benchmark, and prints JSON lines so the orchestrator can parse them. Does **not** call any cloud API.

| Part | What it does |
|------|---------------|
| **Imports** | Tries to import `torch`. If it works, `HAS_TORCH = True`; otherwise we can still use `nvidia-smi` for GPU info. |
| **gpu_info()** | If PyTorch + CUDA: `torch.cuda.get_device_name(0)`, total memory, device count. Else: runs `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits` and parses the first line. Returns dict: gpu_name, gpu_memory_gb, cuda_available, (optional) error. |
| **run_compute_benchmark(secs)** | If no PyTorch/CUDA, returns an error dict. Otherwise: creates two 8192×8192 float32 matrices on `cuda:0`, then for `secs` seconds runs `torch.matmul(a, b)` in a loop with sync. Computes total FLOPs (2×n³ per matmul), then throughput = total_flops / elapsed / 1e9 (GFLOPS). Returns elapsed_sec, steps, throughput_gflops, matrix_size. |
| **main()** | 1) Sets `provider` from env `BENCHMARK_PROVIDER` (runpod/vast). 2) Calls `gpu_info()`, prints one JSON line: `{"event": "gpu_info", "provider": ..., "gpu": {...}}`. 3) If gpu has an error, prints error JSON and exits. 4) Reads `BENCHMARK_COMPUTE_SEC` from env (default 10). 5) Runs `run_compute_benchmark(bench_secs)`, prints: `{"event": "compute_benchmark", ...}`. 6) Prints final line: `{"event": "summary", "provider", "gpu_name", "gpu_memory_gb", "throughput_gflops", "compute_elapsed_sec"}`. |

So: **run_benchmark_on_machine = “report GPU info → run matrix multiply for N seconds → print summary JSON.”** The orchestrator only needs the last line (event `"summary"`) to build the comparison.

---

## 8. End-to-end flow (one run)

1. You: `python run_comparison.py` (laptop).
2. **main()** loads config, finds SSH key, prints budget limit.
3. **RunPod branch**  
   - **runpod_client.create_pod** → RunPod creates a pod, returns id.  
   - **runpod_client.wait_until_running** → we poll until pod is RUNNING and has publicIp + SSH port.  
   - **runpod_client.get_ssh_info** → (host, port).  
   - **run_remote.run_script_ssh** → SCP script to pod, SSH run `python3 /tmp/run_benchmark_on_machine.py` with `BENCHMARK_PROVIDER=runpod` and timeout from $5 limit.  
   - On the **pod**, **run_benchmark_on_machine.main()** runs: gpu_info → compute benchmark → print JSON lines (including `"event": "summary"`).  
   - **run_comparison.parse_benchmark_output** reads stdout, gets summary.  
   - **run_comparison** computes estimated cost (capped at $5), then **runpod_client.terminate_pod** in `finally`.  
4. **Vast branch**  
   - **vast_client.launch_and_wait** → search offers, create instance, wait until running with SSH.  
   - **vast_client.get_ssh_info** → (host, port).  
   - **run_remote.run_script_ssh** → same SCP + SSH, `BENCHMARK_PROVIDER=vast`, timeout from $5.  
   - On the **instance**, same benchmark script runs and prints JSON.  
   - Parse, cost (capped at $5), then **vast_client.destroy_instance** in `finally`.  
5. **main()** prints the comparison table and writes **comparison_results.json**.

So: **each provider = create machine → wait for SSH → copy and run benchmark on machine → parse output and cap cost at $5 → delete machine.** The only code that runs on the GPU is `run_benchmark_on_machine.py`; everything else runs on your laptop and talks to cloud APIs and SSH.

---

## Summary table

| File | Runs on | Purpose |
|------|---------|--------|
| **config.py** | Laptop (imported) | Budget ($5), GPU types, image, disk, timeouts. |
| **run_comparison.py** | Laptop | Orchestrate: create → wait → run benchmark via SSH → parse → terminate; print and save comparison. |
| **runpod_client.py** | Laptop | RunPod API: create pod, wait until RUNNING + SSH, get (host, port), terminate. |
| **vast_client.py** | Laptop | Vast API: search offers, create instance, wait until running + SSH, get (host, port), destroy. |
| **run_remote.py** | Laptop | SCP script to host, SSH run it; return stdout/stderr. |
| **run_benchmark_on_machine.py** | GPU machine (RunPod or Vast) | GPU info + matrix multiply benchmark; print JSON (including summary). |

The **$5 limit** is enforced by: (1) capping the **benchmark timeout** so runtime cannot exceed the budget, and (2) capping **estimated_cost** at `BUDGET_LIMIT_USD` when reporting.
