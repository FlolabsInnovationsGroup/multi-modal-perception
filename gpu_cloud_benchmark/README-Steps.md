GPU benchmark: step-by-step (boring details)
What you actually run
You run one command on your laptop:
python run_comparison.py
python run_comparison.py
Everything else is triggered from that script. Your laptop talks to RunPod and Vast.ai over HTTP, then SSHes into the machines they give you and runs a single Python script on each. No GPU is required on your laptop.
Step 1: Imports and config
When run_comparison.py starts:
It adds its own directory to sys.path so it can import the other modules in gpu_cloud_benchmark.
It imports from config.py: budget, GPU types, images, disk size, timeouts, etc.
It imports from run_remote, runpod_client, and vast_client.
So before any API calls, the process is: load config (from config.py and env), then load the clients and the remote-runner.
Step 2: config.py (what the numbers mean)
config.py is only read when other modules import it. It defines:
Budget: BUDGET_PER_PROVIDER_USD from env GPU_BENCHMARK_BUDGET (default 5.0). BUDGET_LIMIT_USD = 5.0 is a hard cap used for timeouts and reported cost.
RunPod GPUs: RUNPOD_GPU_TYPE_IDS — list of GPU type IDs RunPod will choose from (e.g. A100 80GB PCIe, A100-SXM4-80GB).
Vast GPU: VAST_GPU_NAME (e.g. "A100") used when searching Vast offers.
Images: RUNPOD_IMAGE and VAST_IMAGE — Docker image name (same PyTorch+CUDA image for both for a fair comparison).
Disk: CONTAINER_DISK_GB (e.g. 100).
Timeouts: POD_STARTUP_TIMEOUT_SEC (e.g. 600) for “machine is up and SSH works”, and BENCHMARK_TIMEOUT_SEC (e.g. 3600) as a max for the benchmark script.
Paths: REPO_ROOT and BENCHMARK_SCRIPT_NAME so the orchestrator can find run_benchmark_on_machine.py.
So config = “how much to spend, which GPU/image/disk, how long we’re willing to wait.”
Step 3: main() in run_comparison.py — top-level flow
main() does the following in order.
3.1 Budget and SSH key
Sets budget = min(BUDGET_LIMIT_USD, BUDGET_PER_PROVIDER_USD) (effectively capped at $5 per provider).
Prints something like: Budget limit: $5.0 per provider (RunPod and Vast).
Looks for an SSH key: env SSH_KEY_PATH, else ~/.ssh/id_ed25519, else ~/.ssh/id_rsa. If none exists, it still continues but warns you; SCP/SSH will fail unless that key is added to RunPod and Vast.
3.2 Price check and confirmation
If RUNPOD_API_KEY is set: calls RunPod’s API (via get_gpu_prices) to get price per hour for the configured GPU types and prints them.
If VAST_API_KEY is set: calls Vast (via get_cheapest_offer_price) to get the cheapest A100 offer price and prints it.
Asks: “Proceed with benchmark (will create machines and run tests)? [y/N]”. Unless AUTO_CONFIRM=1 or --yes/-y, a non-yes answer exits here.
3.3 Run RunPod benchmark
If RUNPOD_API_KEY is set, calls run_runpod_benchmark(ssh_key, budget). That function does all RunPod steps (create pod → wait → SSH → run script → parse → terminate). Result is stored in results["runpod"].
3.4 Run Vast benchmark
If VAST_API_KEY is set, calls run_vast_benchmark(ssh_key, budget). Same idea for Vast. Result in results["vast"].
3.5 Print comparison and save JSON
Loops over results and prints for each provider: startup time, total time, estimated cost, GPU name, memory, throughput (GFLOPS). Errors and “skipped” are printed too.
Writes the full results dict to gpu_cloud_benchmark/comparison_results.json.
So at the top level: main = “print budget → show prices → confirm → run RunPod → run Vast → print table → save JSON.”
Step 4: RunPod path in detail — run_runpod_benchmark()
This function implements the full RunPod lifecycle.
4.1 Create pod
Prints “Creating RunPod pod (A100 80GB)...”.
Calls create_pod(...) from runpod_client with: name, image, GPU type IDs from config, 1 GPU, container disk.
Inside runpod_client.create_pod():
Builds headers with RUNPOD_API_KEY.
POST https://rest.runpod.io/v1/pods with JSON: name, imageName, gpuTypeIds, gpuCount, containerDiskInGb, cloudType, ports "22/tcp", supportPublicIp true.
Returns the pod object; the caller keeps pod_id = pod["id"].
4.2 Wait until pod is usable
started_at = time.monotonic().
Calls runpod_wait(pod_id, POD_STARTUP_TIMEOUT_SEC) (i.e. runpod_client.wait_until_running).
Inside wait_until_running():
Every 15 seconds, GET .../pods/{pod_id}.
Checks that status is RUNNING, and that publicIp and a port mapping for 22 exist.
When both are true, returns the pod; otherwise keeps polling until POD_STARTUP_TIMEOUT_SEC.
If timeout is hit, raises TimeoutError.
Back in run_runpod_benchmark: gets (host, port) = get_ssh_info(pod) from the pod (publicIp and port for 22). Computes startup_sec = time.monotonic() - started_at and prints SSH and “ready in Xs”.
4.3 Optional “start benchmark?” confirmation
Asks “Start benchmark on RunPod now? [y/N]”. If user says no, the function returns a result dict with skipped: True and then the finally block still runs (terminate pod). So the pod is always terminated.
4.4 Run the benchmark on the pod (SSH + script)
Sets cost_per_hr = 1.39 (RunPod A100 ballpark).
Computes max_bench_sec = min(900, int((BUDGET_LIMIT_USD / cost_per_hr) * 3600)) so the remote benchmark is not allowed to run longer than the $5 budget allows.
Calls run_script_ssh(host, port, user="root", ssh_key_path=..., env={"BENCHMARK_PROVIDER": "runpod"}, timeout=max_bench_sec).
Inside run_remote.run_script_ssh():
SCP:
Builds scp -o StrictHostKeyChecking=no -o ConnectTimeout=30 -P {port} [-i key] {script_path} root@{host}:/tmp/run_benchmark_on_machine.py.
The file copied is your local run_benchmark_on_machine.py.
If SCP fails, returns (scp.returncode, stdout, stderr) and the caller sees a non-zero return code.
SSH run:
Builds: ssh ... root@{host} "cd /tmp && BENCHMARK_PROVIDER=\"runpod\" python3 /tmp/run_benchmark_on_machine.py".
Runs it with subprocess.run, capture_output=True, text=True, timeout=max_bench_sec.
Returns (returncode, stdout, stderr).
So the only code that runs on the GPU machine is that one Python script; it’s the same file for both RunPod and Vast, with only the env var differing.
4.5 What runs on the GPU machine — run_benchmark_on_machine.py
Execution on the cloud (RunPod pod here):
Imports: Tries to import torch; sets HAS_TORCH True/False. No cloud API is called.
Provider: Reads BENCHMARK_PROVIDER from env (here "runpod").
GPU info: Calls gpu_info().
If PyTorch and CUDA are available: torch.cuda.get_device_name(0), total memory, device count.
Else: runs nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits and parses the first line.
Returns a dict (gpu_name, gpu_memory_gb, cuda_available, etc.).
Prints one JSON line: {"event": "gpu_info", "provider": "runpod", "gpu": {...}}.
If gpu_info has an error: Prints {"event": "error", "message": ...} and exits with code 1.
Compute benchmark: Reads BENCHMARK_COMPUTE_SEC from env (default 10). Calls run_compute_benchmark(secs).
Inside run_compute_benchmark():
If no PyTorch/CUDA, returns an error dict.
Creates two 8192×8192 float32 matrices on cuda:0, syncs.
For secs seconds, runs torch.matmul(a, b) in a loop with torch.cuda.synchronize() after each, counts steps.
total FLOPs = 2×n³ per matmul × steps; throughput = total_flops / elapsed_sec / 1e9 (GFLOPS).
Returns elapsed_sec, steps, throughput_gflops, matrix_size.
Prints: {"event": "compute_benchmark", ...} (that return dict).
Summary: Builds a dict with event "summary", provider, gpu_name, gpu_memory_gb, throughput_gflops, compute_elapsed_sec. Prints that as one JSON line.
So on the machine: report GPU → run matrix multiply for N seconds → print summary. All output is JSON lines to stdout.
4.6 Back on the laptop: parse and cost
run_runpod_benchmark gets back (ret, stdout, stderr) from run_script_ssh. It may print stderr and return code if something failed.
Calls parse_benchmark_output(stdout).
parse_benchmark_output(): Splits stdout by newline, for each line tries json.loads(line). When it finds an object with event == "summary", it returns that object. So the orchestrator only cares about the summary line for the comparison table.
Computes elapsed = time.monotonic() - started_at (total time since pod creation).
estimated_cost = min(BUDGET_LIMIT_USD, (elapsed / 3600) * cost_per_hr) so reported cost never exceeds $5.
Builds the return dict: provider, pod_id, startup_sec, total_elapsed_sec, estimated_cost_usd, summary, etc.
4.7 Cleanup
In a finally block (always run, even on exception or skip): prints “Terminating RunPod pod...”, then calls terminate_pod(pod_id).
runpod_client.terminate_pod(): DELETE https://rest.runpod.io/v1/pods/{pod_id}. Billing stops and the pod is removed.
So RunPod path = “create pod → wait until RUNNING + SSH → optionally confirm → SCP script + SSH run it (with timeout from $5) → parse summary from stdout → compute cost (capped) → always terminate pod.”
Step 5: Vast path in detail — run_vast_benchmark()
Same structure as RunPod, but using Vast’s API and instance lifecycle.
5.1 Launch and wait
Prints “Creating Vast.ai instance (A100)...”.
started_at = time.monotonic().
Calls launch_and_wait(gpu_name=VAST_GPU_NAME, num_gpus=1, image=..., disk_gb=..., label=..., timeout_sec=POD_STARTUP_TIMEOUT_SEC).
Inside vast_client.launch_and_wait():
Search offers: search_offers(gpu_name, num_gpus, min_gpu_ram=80).
search_offers(): PUT https://console.vast.ai/api/v0/search/asks/ with a query: verified, num_gpus, rentable, cuda_max_good, optional gpu_name and gpu_ram; order by dph_total asc. Returns list of offers; each has an id (ask id).
Takes the first (cheapest) offer, gets offer_id.
Create instance: create_instance(offer_id, image, disk_gb, label, runtype="ssh").
create_instance(): PUT .../asks/{offer_id}/ with image, disk, label, runtype "ssh", target_state "running". Response has new_contract (instance id). Returns that id.
Wait: wait_until_running(instance_id, timeout_sec).
wait_until_running(): Polls get_instance(instance_id) until status is "running" and get_ssh_info(inst) returns non-None (host and port). Then returns the instance dict.
Returns (instance_id, inst).
Back in run_vast_benchmark: vast_get_ssh_info(inst) gives (host, port) (tries public_ip, host, connection.host, and various port fields). startup_sec = time.monotonic() - started_at. Prints instance id and SSH.
5.2 Confirm, run benchmark, parse, cost
Same “Start benchmark on Vast now?” confirmation; if no, returns skipped and finally still destroys the instance.
Cost: dph = inst.get("dph_total") or inst.get("price") or 2.0, cost_per_hr = float(dph).
max_bench_sec = min(900, int((BUDGET_LIMIT_USD / cost_per_hr) * 3600)).
run_script_ssh(..., env={"BENCHMARK_PROVIDER": "vast"}, timeout=max_bench_sec) — same SCP + SSH as RunPod; the script runs again on this machine and prints the same JSON events, including "summary".
parse_benchmark_output(stdout) and estimated_cost = min(BUDGET_LIMIT_USD, ...) as for RunPod.
Return dict includes provider, instance_id, startup_sec, total_elapsed_sec, estimated_cost_usd, dph_total, summary, etc.
5.3 Cleanup
In finally: if instance_id is set, prints “Destroying Vast instance...”, then destroy_instance(instance_id).
vast_client.destroy_instance(): DELETE .../instances/{id}/. Instance is destroyed and billing stops.
So Vast path = “search cheapest A100 offer → create instance from that offer → wait until running + SSH → optionally confirm → SCP + SSH same benchmark script (with $5-capped timeout) → parse summary → cost (capped) → always destroy instance.”
Step 6: End-to-end order (single full run)
You: python run_comparison.py (laptop).
main: load config, resolve budget and SSH key, print budget.
main: fetch and print RunPod and Vast prices; ask “Proceed?”; if no, exit.
RunPod: create_pod → wait_until_running (poll pod until RUNNING + publicIp + port 22) → get_ssh_info → “Start benchmark?” → run_script_ssh (SCP script, then SSH run python3 /tmp/run_benchmark_on_machine.py with BENCHMARK_PROVIDER=runpod and timeout from $5) → on the pod the script runs gpu_info → compute benchmark → prints JSON lines including "summary" → run_comparison parses stdout for summary → computes cost (capped) → finally terminate_pod.
Vast: launch_and_wait (search_offers → create_instance → wait_until_running) → get_ssh_info → “Start benchmark?” → run_script_ssh with BENCHMARK_PROVIDER=vast and $5-capped timeout → same script on the instance → parse summary → cost (capped) → finally destroy_instance.
main: print comparison table (startup, total time, cost, GPU, throughput for each provider), write comparison_results.json.
So: each provider = create machine → wait for SSH → copy and run the same benchmark script on the machine → parse the summary line from stdout and cap reported cost at $5 → delete the machine. The only code that runs on the GPU is run_benchmark_on_machine.py; everything else runs on your laptop (config, HTTP APIs, SSH/SCP, parsing, and cleanup).
Summary table (where each piece runs)
File / layer	Runs on	Role
config.py	Laptop	Budget, GPU types, image, disk, timeouts (imported by others).
run_comparison.py	Laptop	Orchestrate: create → wait → run benchmark via SSH → parse → terminate; print comparison and save JSON.
runpod_client.py	Laptop	RunPod REST: create pod, wait until RUNNING + SSH, get (host, port), terminate.
vast_client.py	Laptop	Vast REST: search offers, create instance, wait until running + SSH, get (host, port), destroy.
run_remote.py	Laptop	SCP script to host, SSH run it; return (returncode, stdout, stderr).
run_benchmark_on_machine.py	GPU machine (RunPod or Vast)	GPU info + matrix multiply benchmark; print JSON lines (gpu_info, compute_benchmark, summary).
The $5 limit is enforced by: (1) capping the benchmark timeout so the remote script cannot run longer than the budget allows, and (2) capping estimated_cost at BUDGET_LIMIT_USD when reporting.