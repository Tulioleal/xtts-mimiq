# Base con CUDA 12.1 + Python 3.11
# Vast.ai necesita una imagen con soporte CUDA para usar la GPU
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TTS_HOME=/app/model

# Dependencias del sistema
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Alias python
RUN ln -s /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar el modelo XTTS v2 durante el build de la imagen.
# Esto es clave: el modelo (~2GB) queda dentro de la imagen, asi
# cuando Vast.ai levanta el container, NO hay que esperar la descarga.
RUN python -c "\
from TTS.api import TTS; \
import os; \
os.makedirs('/app/model', exist_ok=True); \
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2'); \
print('Model downloaded successfully')"

# Copiar codigo fuente
COPY src/ ./src/

# Puerto en el que escucha el servidor FastAPI
EXPOSE 8000

# Script de entrypoint que obtiene la IP publica antes de arrancar el servidor
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
