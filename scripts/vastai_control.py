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


import subprocess
import json

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
            and o.get("verified", False)
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


def start_instance():
    """Crea y arranca una nueva instancia con la imagen de PVC TTS."""
    # Chequear si ya hay una instancia corriendo
    existing = get_running_instance()
    if existing:
        print(f"Instance already running: ID={existing['id']} "
              f"Status={existing['actual_status']}")
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
    }

    body = {
        "image": image,
        "disk": 40,
        "env": {k: v for k, v in env_vars.items() if v},
        "ports": "8000/tcp"
    }
        
    result = api_put(
        f"/asks/{offer_id}/",
        body
    )

    instance_id = result.get("new_contract")
    if not instance_id:
        print(f"Unexpected response: {result}")
        sys.exit(1)

    # Inyectar el VAST_INSTANCE_ID una vez que sabemos el ID
    # (lo necesita el watchdog para poder auto-destruirse)
    print(f"Instance created: ID={instance_id}")
    print("Waiting for instance to boot (this may take 3-5 minutes)...")

    _wait_until_running(instance_id)

    info = api_get(f"/instances/{instance_id}/")
    info = info.get("instances", info)  # la API a veces devuelve el objeto directo
    print_connection_info(info)

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
    ports = instance.get("ports", {})
    mapped_port = "unknown"
    if ports:
        port_info = ports.get("8000/tcp", [{}])
        if port_info:
            mapped_port = port_info[0].get("HostPort", "unknown")

    print(f"\nConnection:")
    print(f"  IP:   {ip}")
    print(f"  Port: {mapped_port}")
    print(f"  URL:  http://{ip}:{mapped_port}")
    print(f"\nTest with:")
    print(f"  curl http://{ip}:{mapped_port}/health")


def _wait_until_running(instance_id: str, max_wait: int = 600):
    """Espera hasta que la instancia este en estado 'running'."""
    deadline = time.time() + max_wait
    dots = 0
    while time.time() < deadline:
        try:
            data = api_get(f"/instances/{instance_id}/")
            inst = data if "actual_status" in data else data.get("instances", {})
            status_val = inst.get("actual_status", "unknown") if isinstance(inst, dict) else "unknown"
        except Exception:
            status_val = "unknown"

        print(f"\r  [{status_val}] {'.' * (dots % 4 + 1)}   ", end="", flush=True)
        dots += 1

        if status_val == "running":
            print("\n  Instance is running!")
            return

        time.sleep(15)

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
