"""
Servidor FastAPI que corre DENTRO de la instancia Vast.ai.
Expone un endpoint REST para recibir texto + audio de referencia
y devolver el audio sintetizado.

Al arrancar, se registra en el backend GCP para que este sepa su direccion.
"""

import os
import sys
import logging
import tempfile
import time
import requests
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import Response

# Agrega el directorio raiz al path para imports relativos
sys.path.insert(0, "/app/src")

from inference.xtts_wrapper import XTTSWrapper
from watchdog.watchdog import Watchdog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="PVC TTS Service", version="1.0.0")

# Singletons globales — se inicializan en el startup
wrapper = XTTSWrapper()
watchdog = Watchdog()


@app.on_event("startup")
async def startup():
    logger.info("Loading XTTS v2 model...")
    wrapper.load()
    watchdog.start()
    _register_with_backend()
    logger.info("TTS Service ready.")


@app.get("/health")
def health():
    """El backend GCP usa este endpoint para saber si la instancia esta lista."""
    return {"status": "ready", "model": "xtts_v2"}


@app.post("/synthesize")
async def synthesize(
    text: str = Form(..., description="Texto a sintetizar"),
    language: str = Form(default="es", description="Codigo de idioma: es, en, fr, de, etc."),
    speaker_wav: UploadFile = File(..., description="Archivo WAV de referencia de voz"),
):
    """
    Recibe texto + archivo WAV de referencia y devuelve un archivo WAV sintetizado.

    - text: el texto que se quiere convertir a voz
    - language: idioma del texto (es, en, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja, hu, ko)
    - speaker_wav: archivo de audio con la voz de referencia (idealmente 1-2 minutos, WAV o MP3)
    """
    watchdog.reset()

    # Validar que el archivo es de audio
    if speaker_wav.content_type not in ("audio/wav", "audio/mpeg", "audio/mp3", "audio/x-wav", "application/octet-stream"):
        logger.warning(f"Unexpected content type: {speaker_wav.content_type}")
        # No bloqueamos por content_type porque los clientes a veces mandan 'application/octet-stream'

    if not text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    # Guardar el archivo de referencia en un temporal
    suffix = ".wav" if "wav" in (speaker_wav.filename or "") else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        content = await speaker_wav.read()
        f.write(content)
        speaker_wav_path = f.name

    try:
        logger.info(f"Synthesizing {len(text)} chars in language '{language}'...")
        wav_bytes = wrapper.generate(
            text=text,
            speaker_wav_path=speaker_wav_path,
            language=language,
        )
        logger.info(f"Done. Output size: {len(wav_bytes)} bytes")

        return Response(
            content=wav_bytes,
            media_type="audio/ogg",  # ← cambiar
            headers={"Content-Disposition": "attachment; filename=output.ogg"},  # ← cambiar
        )

    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        os.unlink(speaker_wav_path)


def _register_with_backend():
    """
    Al arrancar, le notifica al backend GCP la direccion de este servicio
    para que pueda enrutar requests hacia aca.
    """
    backend_url = os.environ.get("BACKEND_URL")
    internal_key = os.environ.get("INTERNAL_SECRET")
    instance_id = os.environ.get("VAST_INSTANCE_ID")
    my_ip = os.environ.get("MY_PUBLIC_IP")
    port = os.environ.get("PORT", "8000")
    attempts = int(os.environ.get("BACKEND_REGISTER_ATTEMPTS", "5"))
    retry_delay_seconds = int(os.environ.get("BACKEND_REGISTER_RETRY_DELAY_SECONDS", "5"))

    if not backend_url:
        logger.warning("BACKEND_URL not set. Skipping backend registration.")
        return

    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(
                f"{backend_url}/internal/tts-ready",
                json={
                    "endpoint": f"http://{my_ip}:{port}",
                    "instance_id": instance_id,
                },
                headers={"X-Internal-Key": internal_key},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info(f"Registered with backend: {resp.status_code}")
            return
        except Exception as e:
            logger.warning(f"Registration attempt {attempt}/{attempts} failed: {e}")
            if attempt == attempts:
                logger.error("Failed to register with backend after all retry attempts.")
                return
            time.sleep(retry_delay_seconds)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
