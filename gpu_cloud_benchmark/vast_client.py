"""
Vast.ai client: search offers, create instance, wait until running, get SSH info, destroy.
Uses REST API (console.vast.ai/api/v0). Requires VAST_API_KEY.
"""
import os
import time
import requests

VAST_BASE = "https://console.vast.ai/api/v0"
DEFAULT_HEADERS = {"Content-Type": "application/json"}


def _headers():
    key = os.getenv("VAST_API_KEY")
    if not key:
        raise ValueError("VAST_API_KEY environment variable is required")
    return {**DEFAULT_HEADERS, "Authorization": f"Bearer {key}"}


def search_offers(
    gpu_name: str = "A100",
    num_gpus: int = 1,
    min_gpu_ram: float = 80,
    order: str = "price",
) -> list[dict]:
    """Search for GPU offers. Returns list of offer dicts with 'id' (ask id)."""
    # Vast.ai API: POST /api/v0/bundles/ with flat body (see docs.vast.ai/api-reference/search/search-offers)
    # gpu_ram is in MB; min_gpu_ram is in GB so convert
    body = {
        "limit": 100,
        "type": "ondemand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"gte": num_gpus},
        "order": [["dph_total", "asc"]],
    }
    if gpu_name:
        # Vast lists GPUs with various names; try common A100 variants (UI shows "1x A100 SXM4")
        if gpu_name.upper() == "A100":
            body["gpu_name"] = {"in": ["A100", "A100 SXM4", "A100-SXM4", "NVIDIA A100-SXM4-80GB", "NVIDIA A100 80GB PCIe", "A100-SXM4-80GB", "NVIDIA A100"]}
        else:
            body["gpu_name"] = {"eq": gpu_name}
    if min_gpu_ram:
        body["gpu_ram"] = {"gte": int(min_gpu_ram * 1024)}  # GB -> MB
    r = requests.post(
        f"{VAST_BASE}/bundles/",
        json=body,
        headers=_headers(),
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "offers" in data:
        return data["offers"]
    if isinstance(data, list):
        return data
    return []


def get_cheapest_offer_price(
    gpu_name: str = "A100",
    num_gpus: int = 1,
    min_gpu_ram: float = 80,
) -> tuple[float | None, str]:
    """
    Return (dollars_per_hour, description) for the cheapest matching offer, or (None, error_msg).
    Tries A100 by name first, then falls back to any GPU with min_gpu_ram (e.g. 80GB).
    """
    offers = search_offers(gpu_name=gpu_name, num_gpus=num_gpus, min_gpu_ram=min_gpu_ram)
    if not offers and gpu_name:
        # Fallback: any GPU with enough RAM (Vast may use different GPU name strings)
        offers = search_offers(gpu_name="", num_gpus=num_gpus, min_gpu_ram=min_gpu_ram)
    if not offers:
        return None, f"No offers found for {gpu_name or 'any'} ({num_gpus} GPU, {min_gpu_ram}GB+ RAM)"
    o = offers[0]
    dph = o.get("dph_total") or o.get("price")
    if dph is not None:
        return float(dph), f"{o.get('gpu_name', gpu_name or 'GPU')} @ ${float(dph):.2f}/hr (cheapest)"
    return None, "Offer found but price not in response"


def create_instance(
    offer_id: int,
    image: str,
    disk_gb: int = 100,
    label: str = "benchmark",
    runtype: str = "ssh",
) -> int:
    """Create instance from an offer (ask) id. Returns new contract (instance) id."""
    payload = {
        "image": image,
        "disk": disk_gb,
        "label": label,
        "runtype": runtype,
        "target_state": "running",
    }
    r = requests.put(
        f"{VAST_BASE}/asks/{offer_id}/",
        json=payload,
        headers=_headers(),
        timeout=60,
    )
    r.raise_for_status()
    out = r.json()
    contract_id = out.get("new_contract") or out.get("id")
    if contract_id is None:
        raise ValueError(f"Create instance response missing new_contract: {out}")
    return int(contract_id)


def list_instances() -> list:
    """List user's instances (contracts)."""
    r = requests.get(f"{VAST_BASE}/instances/", headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "instances" in data:
        return data["instances"]
    return data if isinstance(data, list) else []


def get_instance(instance_id: int) -> dict:
    """Get single instance by id. Unwraps if response is { 'instance': {...} }."""
    r = requests.get(
        f"{VAST_BASE}/instances/{instance_id}/",
        headers=_headers(),
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "instance" in data and len(data) == 1:
        return data["instance"]
    return data


def destroy_instance(instance_id: int) -> None:
    """Destroy (terminate) an instance."""
    r = requests.delete(
        f"{VAST_BASE}/instances/{instance_id}/",
        headers=_headers(),
        timeout=60,
    )
    r.raise_for_status()


def wait_until_running(
    instance_id: int,
    timeout_sec: int = 600,
    poll_interval: int = 15,
) -> dict:
    """Poll until instance is running and has SSH connection info. Returns instance dict."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        inst = get_instance(instance_id)
        status = (inst.get("status") or inst.get("actual_status") or "").lower()
        if status == "running":
            # SSH: public_ip and ssh port (mapped from 22)
            if get_ssh_info(inst):
                return inst
        time.sleep(poll_interval)
    raise TimeoutError(
        f"Instance {instance_id} did not become running with SSH within {timeout_sec}s"
    )


def get_ssh_info(inst: dict) -> tuple[str, int] | None:
    """Extract (host, ssh_port) from instance dict if available. Returns None if not ready."""
    conn = inst.get("connection") or {}
    host = (
        inst.get("public_ip")
        or inst.get("host")
        or conn.get("host")
        or inst.get("external_ip")
    )
    ssh_port = conn.get("port") or inst.get("ssh_port") or inst.get("external_port")
    if ssh_port is None:
        ports = inst.get("port_mapping") or inst.get("ports") or {}
        if isinstance(ports, dict):
            ssh_port = ports.get("22") or ports.get(22)
        elif isinstance(ports, str) and "22" in ports:
            for part in ports.replace(",", " ").split():
                if "22" in part and ":" in part:
                    try:
                        ssh_port = int(part.split(":")[-1].strip())
                    except ValueError:
                        pass
                    break
    if host and ssh_port is not None:
        return (str(host), int(ssh_port))
    return None


def launch_and_wait(
    gpu_name: str = "A100",
    num_gpus: int = 1,
    image: str = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
    disk_gb: int = 100,
    label: str = "internvl-benchmark",
    timeout_sec: int = 600,
) -> tuple[int, dict]:
    """Search for cheapest offer, create instance, wait until running. Returns (instance_id, instance)."""
    offers = search_offers(gpu_name=gpu_name, num_gpus=num_gpus, min_gpu_ram=80)
    if not offers:
        raise RuntimeError(f"No Vast.ai offers found for {gpu_name} with {num_gpus} GPU(s)")
    offer = offers[0]
    offer_id = offer.get("id") or offer.get("ask_contract_id") or offer.get("ask_id")
    if offer_id is None:
        raise ValueError(f"Offer missing id: {offer}")
    instance_id = create_instance(
        offer_id=int(offer_id),
        image=image,
        disk_gb=disk_gb,
        label=label,
    )
    inst = wait_until_running(instance_id, timeout_sec=timeout_sec)
    return instance_id, inst
