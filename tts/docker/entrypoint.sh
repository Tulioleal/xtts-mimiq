#!/bin/bash
set -e

echo "[entrypoint] Starting PVC TTS Service..."

# Obtener la IP publica de esta instancia Vast.ai
# Vast.ai no inyecta la IP directamente, la obtenemos de un servicio externo
export MY_PUBLIC_IP=$(curl -s https://api.ipify.org)
echo "[entrypoint] Public IP: $MY_PUBLIC_IP"

# El puerto lo define Vast.ai via variable de entorno o usamos 8000
export PORT=${PORT:-8000}
echo "[entrypoint] Port: $PORT"

echo "[entrypoint] Launching FastAPI server..."
exec python /app/src/streaming/server.py
