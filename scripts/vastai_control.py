#!/usr/bin/env python3
"""
Scripts para prender y apagar la instancia Vast.ai manualmente.

Uso:
  python vastai_control.py start
  python vastai_control.py stop
  python vastai_control.py status

Variables de entorno requeridas:
  VAST_API_KEY        — tu API key de Vast.ai
  DOCKERHUB_USERNAME  — para saber que imagen usar

Variables opcionales:
  VAST_INSTANCE_ID    — si ya tenes una instancia y queres apagarla sin buscar
"""

import sys
import os
import time
import requests
import json

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

API_BASE = "https://console.vast.ai/api/v0"
API_KEY = os.environ["VAST_API_KEY"]
DOCKERHUB_USERNAME = os.environ.get("DOCKERHUB_USERNAME", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def api_get(path):
    r = requests.get(f"{API_BASE}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def api_post(path, body):
    r = requests.post(f"{API_BASE}{path}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()

def api_put(path, body):
    r = requests.put(f"{API_BASE}{path}", headers=HEADERS, json=body)
    if not r.ok:
        print(f"API error {r.status_code}: {r.text}")  # ← ver el mensaje exacto
    r.raise_for_status()
    return r.json()

def api_delete(path):
    r = requests.delete(f"{API_BASE}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def find_best_offer():
    print(f"Searching for offers...")
    
    r = requests.get(f"{API_BASE}/bundles", headers=HEADERS)
    r.raise_for_status()
    offers = r.json().get("offers", [])
    
    filtered = [
        o for o in offers
            if o.get("reliability2", 0) >= 0.90
            and o.get("rentable", False)
            and o.get("disk_space", 0) >= 30
            and o.get("num_gpus", 0) == 1
            and o.get("gpu_ram", 0) >= 12000
            and (o.get("cuda_max_good", 0) >= 11.8 or o.get("cuda_vers", 0) >= 11.8)
            and o.get("gpu_frac", 0) == 1.0        # GPU dedicada completa, no particionada
            and o.get("direct_port_count", 0) > 0  # tiene puertos directos disponibles
            and (o.get("compute_cap", 0) >= 700 and o.get("compute_cap", 0) <= 860 )   # V100 en adelante, soporte amplio hasta RTX 3090/A100, evita arquitecturas muy nuevas
    ]
    
    if not filtered:
        print(f"No offers found.")
        sys.exit(1)
    
    filtered.sort(key=lambda o: o.get("dph_total", 999))
    best = filtered[0]
    print(f"Best offer: ID={best['id']} GPU={best['gpu_name']} "
          f"Price=${best['dph_total']:.3f}/hr"
          f" Reliability={best.get('reliability2', 0):.2%}"
          f" Disk={best.get('disk_space', 0)}GB"
          f" Rentable={best.get('rentable', False)}"
          f" VRAM={best.get('gpu_ram', 0)  / 1024}GB")
    return best["id"]

def wait_for_health(ip, port, max_wait=300):
    url = f"http://{ip}:{port}/health"
    print(f"Waiting for server to be ready at {url}...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print(f"Server is ready! {r.json()}")
                return
        except Exception:
            pass
        print("  Not ready yet, retrying in 15s...")
        time.sleep(15)
    print("Server did not become healthy in time.")


def start_instance():
    """Crea y arranca una nueva instancia con la imagen de PVC TTS."""
    # Chequear si ya hay una instancia corriendo
    existing = get_running_instance()
    if existing:
        if existing.get("actual_status") != "running":
            print(f"Instance found but not ready: ID={existing['id']} Status={existing['actual_status']}")
            _wait_until_running(existing["id"])
            existing = api_get(f"/instances/{existing['id']}/")
        print(f"Instance already running: ID={existing['id']}")
        print_connection_info(existing)
        return existing["id"]

    offer_id = find_best_offer()

    image = f"{DOCKERHUB_USERNAME}/pvc-tts:latest"
    print(f"Creating instance with image: {image}")

    # Variables de entorno que necesita el container
    env_vars = {
        "VAST_API_KEY": API_KEY,
        "BACKEND_URL": BACKEND_URL,
        "INTERNAL_SECRET": INTERNAL_SECRET,
        "WATCHDOG_TIMEOUT_SECONDS": "1800",
        "NVIDIA_VISIBLE_DEVICES": "all",
    }

    result = api_put(f"/asks/{offer_id}/", {
        "image": image,
        "disk": 40,
        "env": {k: v for k, v in env_vars.items() if v},
        "ports": "8000/tcp",
        "runtype": "ssh",
        "onstart": "bash /app/entrypoint.sh",
    })

    instance_id = result.get("new_contract")
    if not instance_id:
        print(f"Unexpected response: {result}")
        sys.exit(1)


    # Inyectar VAST_INSTANCE_ID ahora que lo sabemos
    api_put(f"/instances/{instance_id}/", {
        "env": {**{k: v for k, v in env_vars.items() if v}, "VAST_INSTANCE_ID": str(instance_id)}
    })

    print(f"Instance created: ID={instance_id}")
    print("Waiting for instance to boot (this may take 3-5 minutes)...")

    _wait_until_running(instance_id)

    info = api_get(f"/instances/{instance_id}/")
    info = info.get("instances", info)
    print_connection_info(info)

    ip = info.get("public_ipaddr")
    ports = info.get("ports", {}) or {}
    port = ports.get("8000/tcp", [{}])[0].get("HostPort")
    if ip and port:
        wait_for_health(ip, port)

    return instance_id


def stop_instance():
    """Destruye la instancia corriendo."""
    instance_id = os.environ.get("VAST_INSTANCE_ID")

    if not instance_id:
        # Buscar automaticamente
        instance = get_running_instance()
        if not instance:
            print("No running PVC TTS instance found.")
            return
        instance_id = instance["id"]

    print(f"Destroying instance {instance_id}...")
    api_delete(f"/instances/{instance_id}/")
    print("Instance destroyed.")


def get_running_instance():
    """Devuelve la primera instancia corriendo con imagen pvc-tts, o None."""
    data = api_get("/instances/")
    instances = data.get("instances", [])
    for inst in instances:
        if "pvc-tts" in inst.get("image_uuid", "") or "pvc-tts" in inst.get("image", ""):
            return inst
    return None


def status():
    """Muestra el estado de la instancia actual."""
    instance = get_running_instance()
    if not instance:
        print("Status: OFFLINE — no running instance found.")
        return

    s = instance.get("actual_status", "unknown")
    print(f"Status: {s.upper()}")
    print(f"Instance ID: {instance['id']}")
    print(f"GPU: {instance.get('gpu_name', 'unknown')}")
    print(f"Price: ${instance.get('dph_total', 0):.3f}/hr")
    print_connection_info(instance)


def print_connection_info(instance):
    ip = instance.get("public_ipaddr", "unknown")
    ports = instance.get("ports", {}) or {}
    
    print(f"DEBUG ports dict: {json.dumps(ports, indent=2)}")  # ← temporal
    
    mapped_port = "unknown"
    
    for key, val in ports.items():
        if "8000" in key and val:
            mapped_port = val[0].get("HostPort", "unknown")
            break

    print(f"\nConnection:")
    print(f"  IP:   {ip}")
    print(f"  Port: {mapped_port}")
    print(f"  URL:  http://{ip}:{mapped_port}")
    print(f"\nTest with:")
    print(f"  curl http://{ip}:{mapped_port}/health")


def _wait_until_running(instance_id: str, max_wait: int = 900):
    deadline = time.time() + max_wait
    dots = 0
    while time.time() < deadline:
        try:
            data = api_get(f"/instances/{instance_id}/")
            inst = data.get("instances", data)
            if isinstance(inst, list):
                inst = inst[0] if inst else {}
            status_val = inst.get("actual_status", "unknown") if isinstance(inst, dict) else "unknown"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            status_val = "unknown"
        except Exception as e:
            print(f"  Error polling: {e}")
            status_val = "unknown"

        print(f"\r  [{status_val}] {'.' * (dots % 4 + 1)}   ", end="", flush=True)
        dots += 1

        if status_val == "running":
            print("\n  Instance is running!")
            return

        time.sleep(30)  # ← 30 en lugar de 15

    print(f"\nTimeout after {max_wait}s. Check Vast.ai dashboard.")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        start_instance()
    elif cmd == "stop":
        stop_instance()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        print("Use: start | stop | status")
        sys.exit(1)
