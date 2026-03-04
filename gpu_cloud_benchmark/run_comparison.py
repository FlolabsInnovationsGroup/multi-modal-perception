#!/usr/bin/env python3
"""
Run GPU benchmark on RunPod and Vast.ai within a budget (~$5 each), then compare.
Requires: RUNPOD_API_KEY, VAST_API_KEY, and SSH key added to both providers.
Optional: SSH_KEY_PATH for scp/ssh (e.g. ~/.ssh/id_ed25519).
Set AUTO_CONFIRM=1 or pass --yes to skip confirmation prompts.
"""
import json
import os
import sys
import time
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    BUDGET_LIMIT_USD,
    BUDGET_PER_PROVIDER_USD,
    CONTAINER_DISK_GB,
    POD_STARTUP_TIMEOUT_SEC,
    RUNPOD_GPU_TYPE_IDS,
    RUNPOD_IMAGE,
    VAST_GPU_NAME,
    VAST_IMAGE,
)
from run_remote import run_script_ssh
from runpod_client import (
    create_pod,
    get_gpu_prices,
    get_ssh_info,
    terminate_pod,
    wait_until_running as runpod_wait,
)
from vast_client import (
    destroy_instance,
    get_cheapest_offer_price,
    get_ssh_info as vast_get_ssh_info,
    launch_and_wait,
)

AUTO_CONFIRM = os.getenv("AUTO_CONFIRM", "").strip().lower() in ("1", "true", "yes")


def confirm(prompt: str, default_no: bool = True) -> bool:
    """Ask user to confirm. Returns True for yes, False for no. Skips if AUTO_CONFIRM or --yes."""
    if AUTO_CONFIRM or "--yes" in sys.argv or "-y" in sys.argv:
        return True
    default = "y" if not default_no else "n"
    suffix = " [Y/n]: " if not default_no else " [y/N]: "
    try:
        answer = input(prompt + suffix).strip().lower() or default
        return answer in ("y", "yes")
    except EOFError:
        return False


def parse_benchmark_output(stdout: str) -> dict:
    """Parse JSON lines from benchmark script; return summary and full results."""
    results = {}
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            event = obj.get("event")
            if event == "summary":
                return obj
            if event:
                results[event] = obj
        except json.JSONDecodeError:
            pass
    return results.get("summary") or results or {}


def run_runpod_benchmark(ssh_key_path: str | None, budget_usd: float) -> dict:
    """Create RunPod pod, run benchmark, terminate. Return metrics + cost info."""
    print("Creating RunPod pod (A100 80GB)...", flush=True)
    pod = create_pod(
        name="internvl-benchmark",
        image_name=RUNPOD_IMAGE,
        gpu_type_ids=RUNPOD_GPU_TYPE_IDS,
        gpu_count=1,
        container_disk_in_gb=CONTAINER_DISK_GB,
    )
    pod_id = pod.get("id")
    if not pod_id:
        raise RuntimeError(f"RunPod create response missing id: {pod}")
    print(f"  Pod id: {pod_id}", flush=True)

    started_at = time.monotonic()
    try:
        pod = runpod_wait(pod_id, timeout_sec=POD_STARTUP_TIMEOUT_SEC)
        host, port = get_ssh_info(pod)
        startup_sec = time.monotonic() - started_at
        print(f"  SSH: {host}:{port} (ready in {startup_sec:.0f}s)", flush=True)

        # Confirm before starting the actual benchmark
        if not confirm("  Start benchmark on RunPod now?", default_no=True):
            print("  Skipping RunPod benchmark (pod will be terminated).", flush=True)
            return {
                "provider": "runpod",
                "pod_id": pod_id,
                "startup_sec": round(startup_sec, 1),
                "skipped": True,
                "reason": "user declined to run benchmark",
            }

        # Cap benchmark runtime so we stay under $5 limit (RunPod A100 ~$1.39/hr)
        cost_per_hr = 1.39
        max_bench_sec = min(900, int((BUDGET_LIMIT_USD / cost_per_hr) * 3600))
        ret, stdout, stderr = run_script_ssh(
            host=host,
            port=port,
            user="root",
            ssh_key_path=ssh_key_path,
            env={"BENCHMARK_PROVIDER": "runpod"},
            timeout=max_bench_sec,
        )
        if stderr:
            print("  stderr:", stderr[:500], flush=True)
        if ret != 0:
            print("  Benchmark script exit code:", ret, flush=True)

        summary = parse_benchmark_output(stdout)
        elapsed = time.monotonic() - started_at
        estimated_cost = min(BUDGET_LIMIT_USD, (elapsed / 3600) * cost_per_hr)
        return {
            "provider": "runpod",
            "pod_id": pod_id,
            "startup_sec": round(startup_sec, 1),
            "total_elapsed_sec": round(elapsed, 1),
            "estimated_cost_usd": round(estimated_cost, 4),
            "budget_limit_usd": BUDGET_LIMIT_USD,
            "summary": summary,
            "stdout": stdout,
            "returncode": ret,
        }
    finally:
        print("  Terminating RunPod pod...", flush=True)
        try:
            terminate_pod(pod_id)
        except Exception as e:
            print("  Terminate error:", e, flush=True)

    return {}


def run_vast_benchmark(ssh_key_path: str | None, budget_usd: float) -> dict:
    """Create Vast instance, run benchmark, destroy. Return metrics + cost info."""
    print("Creating Vast.ai instance (A100)...", flush=True)
    started_at = time.monotonic()
    instance_id = None
    try:
        instance_id, inst = launch_and_wait(
            gpu_name=VAST_GPU_NAME,
            num_gpus=1,
            image=VAST_IMAGE,
            disk_gb=CONTAINER_DISK_GB,
            label="internvl-benchmark",
            timeout_sec=POD_STARTUP_TIMEOUT_SEC,
        )
        ssh_info = vast_get_ssh_info(inst)
        if not ssh_info:
            raise RuntimeError("Vast instance running but no SSH info in response")
        host, port = ssh_info
        startup_sec = time.monotonic() - started_at
        print(f"  Instance id: {instance_id}, SSH: {host}:{port} (ready in {startup_sec:.0f}s)", flush=True)

        # Confirm before starting the actual benchmark
        if not confirm("  Start benchmark on Vast now?", default_no=True):
            print("  Skipping Vast benchmark (instance will be destroyed).", flush=True)
            return {
                "provider": "vast",
                "instance_id": instance_id,
                "startup_sec": round(startup_sec, 1),
                "skipped": True,
                "reason": "user declined to run benchmark",
            }

        # Cap benchmark runtime so we stay under $5 limit
        dph = inst.get("dph_total") or inst.get("price") or 2.0
        cost_per_hr = float(dph)
        max_bench_sec = min(900, int((BUDGET_LIMIT_USD / cost_per_hr) * 3600))
        ret, stdout, stderr = run_script_ssh(
            host=host,
            port=port,
            user="root",
            ssh_key_path=ssh_key_path,
            env={"BENCHMARK_PROVIDER": "vast"},
            timeout=max_bench_sec,
        )
        if stderr:
            print("  stderr:", stderr[:500], flush=True)
        if ret != 0:
            print("  Benchmark script exit code:", ret, flush=True)

        summary = parse_benchmark_output(stdout)
        elapsed = time.monotonic() - started_at
        estimated_cost = min(BUDGET_LIMIT_USD, (elapsed / 3600) * cost_per_hr)
        return {
            "provider": "vast",
            "instance_id": instance_id,
            "startup_sec": round(startup_sec, 1),
            "total_elapsed_sec": round(elapsed, 1),
            "estimated_cost_usd": round(estimated_cost, 4),
            "budget_limit_usd": BUDGET_LIMIT_USD,
            "dph_total": dph,
            "summary": summary,
            "stdout": stdout,
            "returncode": ret,
        }
    finally:
        if instance_id is not None:
            print("  Destroying Vast instance...", flush=True)
            try:
                destroy_instance(instance_id)
            except Exception as e:
                print("  Destroy error:", e, flush=True)

    return {}


def main():
    budget = min(BUDGET_LIMIT_USD, BUDGET_PER_PROVIDER_USD)  # Hard cap $5 per provider
    print(f"Budget limit: ${BUDGET_LIMIT_USD} per provider (RunPod and Vast)", flush=True)
    print()

    # --- Step 1: Show price/hr for each provider and confirm to proceed ---
    print("--- Price per hour (current/estimated) ---")
    runpod_price_hr = None
    if os.getenv("RUNPOD_API_KEY"):
        try:
            prices = get_gpu_prices(RUNPOD_GPU_TYPE_IDS)
            for p in prices:
                c = p.get("communityPrice")
                s = p.get("securePrice")
                cstr = f"${c:.2f}" if c is not None else "N/A"
                sstr = f"${s:.2f}" if s is not None else "N/A"
                print(f"  RunPod  {p.get('displayName', p['id'])}:  Community {cstr}/hr  |  Secure {sstr}/hr")
                if runpod_price_hr is None and c is not None:
                    runpod_price_hr = float(c)
        except Exception as e:
            print(f"  RunPod  (could not fetch prices: {e})  using ~$1.39/hr")
            runpod_price_hr = 1.39
    else:
        print("  RunPod  (skip: RUNPOD_API_KEY not set)")

    vast_price_hr = None
    if os.getenv("VAST_API_KEY"):
        try:
            dph, msg = get_cheapest_offer_price(gpu_name=VAST_GPU_NAME, num_gpus=1, min_gpu_ram=80)
            if dph is not None:
                vast_price_hr = dph
                print(f"  Vast.ai  {msg}")
            else:
                print(f"  Vast.ai  {msg}  using ~$2.00/hr")
                vast_price_hr = 2.0
        except Exception as e:
            print(f"  Vast.ai  (could not fetch price: {e})  using ~$2.00/hr")
            vast_price_hr = 2.0
    else:
        print("  Vast.ai  (skip: VAST_API_KEY not set)")

    print()
    if not confirm("Proceed with benchmark (will create machines and run tests)?", default_no=True):
        print("Aborted by user.")
        sys.exit(0)
    print()

    ssh_key = os.getenv("SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_ed25519"))
    if not os.path.isfile(ssh_key):
        ssh_key = os.path.expanduser("~/.ssh/id_rsa")
    if not os.path.isfile(ssh_key):
        ssh_key = None
        print("Warning: No SSH key found. Set SSH_KEY_PATH or use ~/.ssh/id_ed25519 / id_rsa.", flush=True)
        print("You must add your public key to RunPod and Vast.ai for SSH access.", flush=True)

    results = {}
    # RunPod first
    if os.getenv("RUNPOD_API_KEY"):
        try:
            results["runpod"] = run_runpod_benchmark(ssh_key, budget)
        except Exception as e:
            print("RunPod failed:", e, flush=True)
            results["runpod"] = {"error": str(e)}
    else:
        print("Skip RunPod: RUNPOD_API_KEY not set.", flush=True)

    # Vast second
    if os.getenv("VAST_API_KEY"):
        try:
            results["vast"] = run_vast_benchmark(ssh_key, budget)
        except Exception as e:
            print("Vast failed:", e, flush=True)
            results["vast"] = {"error": str(e)}
    else:
        print("Skip Vast: VAST_API_KEY not set.", flush=True)

    # Comparison
    print("\n" + "=" * 60, flush=True)
    print("COMPARISON (InternVL 38B GPU benchmark)", flush=True)
    print("=" * 60, flush=True)
    for provider, data in results.items():
        if "error" in data:
            print(f"  {provider}: ERROR - {data['error']}", flush=True)
            continue
        if data.get("skipped"):
            print(f"  {provider}: SKIPPED - {data.get('reason', 'user declined')}", flush=True)
            continue
        s = data.get("summary") or {}
        print(f"  {provider}:", flush=True)
        print(f"    Startup:     {data.get('startup_sec')} s", flush=True)
        print(f"    Total time: {data.get('total_elapsed_sec')} s", flush=True)
        print(f"    Est. cost:  ${data.get('estimated_cost_usd')}", flush=True)
        print(f"    GPU:        {s.get('gpu_name')} ({s.get('gpu_memory_gb')} GB)", flush=True)
        print(f"    Throughput: {s.get('throughput_gflops')} GFLOPS", flush=True)
    print("=" * 60, flush=True)

    # Write JSON for later use
    out_path = Path(__file__).parent / "comparison_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
