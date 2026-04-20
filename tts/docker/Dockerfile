FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TTS_HOME=/app/model

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# context es la raiz del repo, los paths son relativos a ella
COPY tts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "\
from TTS.api import TTS; \
import os; \
os.makedirs('/app/model', exist_ok=True); \
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2'); \
print('Model downloaded successfully')"

COPY tts/src/ ./src/

EXPOSE 8000

COPY tts/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]