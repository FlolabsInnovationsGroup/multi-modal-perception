"""
RunPod API client: create pod, wait until ready, get SSH info, terminate.
Uses REST API (no SDK dependency for pods). Requires RUNPOD_API_KEY.
"""
import os
import time
import requests

RUNPOD_BASE = "https://rest.runpod.io/v1"
DEFAULT_HEADERS = {"Content-Type": "application/json"}


def _headers():
    key = os.getenv("RUNPOD_API_KEY")
    if not key:
        raise ValueError("RUNPOD_API_KEY environment variable is required")
    return {**DEFAULT_HEADERS, "Authorization": f"Bearer {key}"}


def create_pod(
    name: str,
    image_name: str,
    gpu_type_ids: list[str],
    gpu_count: int = 1,
    container_disk_in_gb: int = 100,
    cloud_type: str = "COMMUNITY",
) -> dict:
    """Create an on-demand GPU pod. Returns pod object with id."""
    payload = {
        "name": name,
        "imageName": image_name,
        "gpuTypeIds": gpu_type_ids,
        "gpuCount": gpu_count,
        "containerDiskInGb": container_disk_in_gb,
        "cloudType": cloud_type,
        "ports": "22/tcp",
        "supportPublicIp": True,  # required for SSH on Community Cloud
    }
    r = requests.post(f"{RUNPOD_BASE}/pods", json=payload, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def get_pod(pod_id: str) -> dict:
    """Get pod by id."""
    r = requests.get(f"{RUNPOD_BASE}/pods/{pod_id}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def list_pods() -> list:
    """List all pods."""
    r = requests.get(f"{RUNPOD_BASE}/pods", headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("data", []) if isinstance(data, dict) else data


def terminate_pod(pod_id: str) -> dict:
    """Terminate (delete) a pod."""
    r = requests.delete(f"{RUNPOD_BASE}/pods/{pod_id}", headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def wait_until_running(pod_id: str, timeout_sec: int = 600, poll_interval: int = 15) -> dict:
    """Poll until pod is RUNNING and has publicIp + portMappings. Returns pod object."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        pod = get_pod(pod_id)
        status = (pod.get("desiredStatus") or pod.get("status") or "").upper()
        if status == "RUNNING":
            public_ip = pod.get("publicIp") or (pod.get("machine") or {}).get("publicIp")
            port_mappings = pod.get("portMappings") or {}
            ssh_port = port_mappings.get(22) or port_mappings.get("22") if isinstance(port_mappings, dict) else None
            if public_ip and ssh_port is not None:
                return pod
        time.sleep(poll_interval)
    raise TimeoutError(f"Pod {pod_id} did not become RUNNING with SSH within {timeout_sec}s")


def get_gpu_prices(gpu_type_ids: list[str]) -> list[dict]:
    """
    Get price per hour for given GPU type ids. Returns list of {id, displayName, communityPrice, securePrice}.
    Uses GET /gpus if available; otherwise returns fallback prices for known A100 types.
    """
    try:
        r = requests.get(f"{RUNPOD_BASE}/gpus", headers=_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        gpus = data if isinstance(data, list) else data.get("data", [])
        by_id = {g.get("id"): g for g in gpus} if isinstance(gpus, list) else {}
        out = []
        for gid in gpu_type_ids:
            g = by_id.get(gid)
            if g:
                out.append({
                    "id": gid,
                    "displayName": g.get("displayName") or gid,
                    "communityPrice": g.get("communityPrice"),
                    "securePrice": g.get("securePrice"),
                })
            else:
                # Fallback for A100 80GB (Community ~$1.19–1.59/hr)
                out.append({
                    "id": gid,
                    "displayName": gid.replace("NVIDIA ", ""),
                    "communityPrice": 1.39,
                    "securePrice": 1.49,
                })
        return out
    except Exception:
        # Fallback when API not available or different shape
        return [
            {"id": gid, "displayName": gid.replace("NVIDIA ", ""), "communityPrice": 1.39, "securePrice": 1.49}
            for gid in gpu_type_ids
        ]


def get_ssh_info(pod: dict) -> tuple[str, int]:
    """Extract (host, port) for SSH from pod object. RunPod: publicIp + portMappings['22']."""
    public_ip = pod.get("publicIp") or (pod.get("machine") or {}).get("publicIp")
    port_mappings = pod.get("portMappings") or {}
    ssh_port = port_mappings.get(22) or port_mappings.get("22") if isinstance(port_mappings, dict) else None
    if not public_ip or ssh_port is None:
        raise ValueError(f"Cannot get SSH info from pod: publicIp={public_ip}, portMappings={port_mappings}")
    return str(public_ip), int(ssh_port)
