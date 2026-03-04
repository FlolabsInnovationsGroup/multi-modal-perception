"""
Run a local script on a remote host via SSH (and optional SCP).
Uses subprocess + ssh/scp. Requires SSH key added to RunPod and Vast.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BENCHMARK_SCRIPT = REPO_ROOT / "run_benchmark_on_machine.py"


def run_script_ssh(
    host: str,
    port: int,
    script_path: Path = BENCHMARK_SCRIPT,
    user: str = "root",
    ssh_key_path: str | None = None,
    env: dict | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """
    Copy script to remote /tmp and run it. Returns (returncode, stdout, stderr).
    """
    remote_path = "/tmp/run_benchmark_on_machine.py"
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30", "-p", str(port)]
    if ssh_key_path:
        ssh_opts.extend(["-i", ssh_key_path])
    base_cmd = ["ssh"] + ssh_opts + [f"{user}@{host}"]

    # Copy script via scp
    scp_opts = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30", "-P", str(port)]
    if ssh_key_path:
        scp_opts.extend(["-i", ssh_key_path])
    scp = subprocess.run(
        ["scp"] + scp_opts + [str(script_path), f"{user}@{host}:{remote_path}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if scp.returncode != 0:
        return scp.returncode, scp.stdout, scp.stderr

    # Build env exports
    env_exports = ""
    if env:
        env_exports = " ".join(f'{k}="{v}"' for k, v in env.items()) + " "

    cmd = base_cmd + [f"cd /tmp && {env_exports}python3 {remote_path}"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr
