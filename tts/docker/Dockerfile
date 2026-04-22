FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TTS_HOME=/app/model
ENV COQUI_TOS_AGREED=1

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

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

COPY tts/requirements.txt ./requirements.txt
COPY tts/src/inference/ ./inference/
COPY tts/src/streaming/server.py ./server.py
COPY tts/src/watchdog/ ./watchdog/
COPY tts/docker/entrypoint.sh ./entrypoint.sh

RUN touch inference/__init__.py watchdog/__init__.py

RUN pip install --no-cache-dir "numpy>=1.23.5,<1.25.0" "transformers>=4.31.0,<4.35.0"
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