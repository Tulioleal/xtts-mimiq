FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TTS_HOME=/app/model

RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-dev \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

WORKDIR /app

COPY tts/requirements.txt ./requirements.txt
COPY tts/src/inference/xtts_wrapper.py ./xtts_wrapper.py
COPY tts/src/streaming/server.py ./server.py
COPY tts/src/watchdog/watchdog.py ./watchdog.py
COPY tts/docker/entrypoint.sh ./entrypoint.sh

# PARCHE DE DEPENDENCIAS:
# Instalamos una versión de NumPy que satisfaga a librosa ANTES de los requirements
RUN pip install --no-cache-dir "numpy>=1.23.5,<1.25.0"
RUN pip install --no-cache-dir -r requirements.txt

RUN python3 -c "\
from TTS.api import TTS; \
import os; \
os.makedirs('/app/model', exist_ok=True); \
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2'); \
print('Model downloaded successfully')"

RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]