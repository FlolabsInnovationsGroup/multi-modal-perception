#!/usr/bin/env python3
"""
Pre-flight check: verify API keys and SSH setup WITHOUT creating any pods or instances.
No credits are used. Run this before run_comparison.py to ensure everything is working.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import RUNPOD_GPU_TYPE_IDS, VAST_GPU_NAME


def check_runpod() -> tuple[bool, str]:
    """Verify RunPod API key and connection. No pods created."""
    if not os.getenv("RUNPOD_API_KEY"):
        return False, "RUNPOD_API_KEY is not set"
    try:
        from runpod_client import get_gpu_prices
        prices = get_gpu_prices(RUNPOD_GPU_TYPE_IDS)
        if not prices:
            return False, "RunPod API responded but no GPU types found"
        return True, f"OK (e.g. {prices[0].get('displayName', 'A100')} ~${prices[0].get('communityPrice', '?')}/hr)"
    except Exception as e:
        return False, str(e)


def check_vast() -> tuple[bool, str]:
    """Verify Vast.ai API key and connection. No instances created."""
    if not os.getenv("VAST_API_KEY"):
        return False, "VAST_API_KEY is not set"
    try:
        from vast_client import get_cheapest_offer_price
        dph, msg = get_cheapest_offer_price(gpu_name=VAST_GPU_NAME, num_gpus=1, min_gpu_ram=80)
        if dph is not None:
            return True, f"OK ({msg})"
        # API responded but no offers: key is valid, inventory may be empty
        return True, f"API OK — {msg} (benchmark may find offers when you run it)"
    except Exception as e:
        return False, str(e)


def check_ssh_key() -> tuple[bool, str]:
    """Verify SSH private key file exists (public key must be added to RunPod & Vast)."""
    ssh_key = os.getenv("SSH_KEY_PATH", os.path.expanduser("~/.ssh/id_ed25519"))
    if os.path.isfile(ssh_key):
        return True, f"OK ({ssh_key})"
    ssh_key = os.path.expanduser("~/.ssh/id_rsa")
    if os.path.isfile(ssh_key):
        return True, f"OK ({ssh_key})"
    return False, "No key at ~/.ssh/id_ed25519 or ~/.ssh/id_rsa (set SSH_KEY_PATH if elsewhere)"


def main():
    print("GPU Cloud Benchmark — Setup check (no credits used)\n", flush=True)
    all_ok = True

    # RunPod
    ok, msg = check_runpod()
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  RunPod API:  [{status}] {msg}")

    # Vast.ai
    ok, msg = check_vast()
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  Vast.ai API: [{status}] {msg}")

    # SSH key
    ok, msg = check_ssh_key()
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  SSH key:     [{status}] {msg}")

    print()
    if all_ok:
        print("All checks passed. You can run:  python run_comparison.py")
        return 0
    print("Fix the items above, then run this script again before using credits.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
