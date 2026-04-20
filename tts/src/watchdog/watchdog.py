import threading
import time
import requests
import os
import logging

logger = logging.getLogger(__name__)

INACTIVITY_TIMEOUT = int(os.environ.get("WATCHDOG_TIMEOUT_SECONDS", 1800))  # 30 min default


class Watchdog:
    """
    Monitorea inactividad y destruye la instancia Vast.ai cuando
    no hubo actividad por INACTIVITY_TIMEOUT segundos.
    """

    def __init__(self):
        self.last_activity = time.time()
        self._lock = threading.Lock()
        self._stopped = False

    def reset(self):
        """Llamar en cada request recibido para resetear el timer."""
        with self._lock:
            self.last_activity = time.time()
        logger.debug("Watchdog timer reset.")

    def start(self):
        thread = threading.Thread(target=self._monitor, daemon=True)
        thread.start()
        logger.info(f"Watchdog started. Timeout: {INACTIVITY_TIMEOUT}s")

    def _monitor(self):
        while not self._stopped:
            time.sleep(60)  # chequea cada minuto
            with self._lock:
                idle_seconds = time.time() - self.last_activity

            logger.debug(f"Watchdog: idle for {idle_seconds:.0f}s / {INACTIVITY_TIMEOUT}s")

            if idle_seconds > INACTIVITY_TIMEOUT:
                logger.info("Watchdog: inactivity timeout reached. Shutting down.")
                self._notify_backend()
                self._destroy_instance()
                break

    def _notify_backend(self):
        """
        Le avisa al backend FastAPI que la instancia va a apagarse,
        para que limpie el endpoint registrado.
        """
        backend_url = os.environ.get("BACKEND_URL")
        internal_key = os.environ.get("INTERNAL_SECRET")
        instance_id = os.environ.get("VAST_INSTANCE_ID")

        if not backend_url:
            return

        try:
            requests.post(
                f"{backend_url}/internal/tts-offline",
                json={"instance_id": instance_id, "reason": "watchdog_timeout"},
                headers={"X-Internal-Key": internal_key},
                timeout=5,
            )
            logger.info("Backend notified of shutdown.")
        except Exception as e:
            logger.warning(f"Failed to notify backend: {e}")

    def _destroy_instance(self):
        """Llama a la API de Vast.ai para destruir esta instancia."""
        instance_id = os.environ.get("VAST_INSTANCE_ID")
        api_key = os.environ.get("VAST_API_KEY")

        if not instance_id or not api_key:
            logger.error("VAST_INSTANCE_ID or VAST_API_KEY not set. Cannot self-destruct.")
            return

        try:
            resp = requests.delete(
                f"https://console.vast.ai/api/v0/instances/{instance_id}/",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            logger.info(f"Vast.ai destroy response: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to destroy instance: {e}")
