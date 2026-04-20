# PVC TTS Service

Servicio de síntesis de voz con XTTS v2 corriendo en una GPU de Vast.ai.

## Arquitectura

```
Tu cliente (curl / frontend)
        │
        │  POST /synthesize  (texto + audio de referencia)
        ▼
  Vast.ai GPU instance
  └── Docker container
      ├── FastAPI server          ← recibe la request
      ├── XTTS v2 (en GPU)       ← genera el audio
      └── Watchdog               ← apaga la instancia tras 30 min de inactividad
```

## Setup inicial

### 1. Configurar secrets en GitHub

En tu repo: **Settings → Secrets and variables → Actions**

| Secret | Valor |
|--------|-------|
| `VAST_API_KEY` | Tu API key de [Vast.ai](https://console.vast.ai/account) |
| `DOCKERHUB_USERNAME` | Tu usuario de Docker Hub |
| `DOCKERHUB_TOKEN` | Access token de Docker Hub |
| `BACKEND_URL` | (Opcional) URL del backend GCP |
| `INTERNAL_SECRET` | (Opcional) Clave interna compartida |

### 2. Build de la imagen Docker

Ir a **Actions → Build & Push TTS Image → Run workflow**

Esto construye la imagen con el modelo XTTS v2 pre-descargado y la sube a Docker Hub.
El modelo pesa ~2GB y queda dentro de la imagen para que la instancia arranque rápido.

> La primera vez tarda ~15 minutos. Los builds siguientes son más rápidos gracias al cache.

### 3. Variables de entorno locales (para usar los scripts)

```bash
cp .env.example .env
# Completar los valores en .env
source .env
```

## Uso

### Prender la instancia

Desde GitHub Actions: **Actions → Start TTS Instance → Run workflow**

O desde la terminal:
```bash
source .env
python scripts/vastai_control.py start
```

El script busca la GPU más barata disponible, crea la instancia, y espera hasta que esté lista.
Tarda **3-5 minutos** en arrancar (boot + carga del modelo).

### Ver estado

```bash
python scripts/vastai_control.py status
```

### Apagar la instancia

Desde GitHub Actions: **Actions → Stop TTS Instance → Run workflow**

O desde la terminal:
```bash
python scripts/vastai_control.py stop
```

La instancia también se apaga **automáticamente** tras 30 minutos de inactividad (watchdog).

---

## Usar el endpoint

Una vez que la instancia está corriendo, el script te muestra la URL:

```
Connection:
  IP:   123.45.67.89
  Port: 12345
  URL:  http://123.45.67.89:12345
```

### Health check

```bash
curl http://IP:PORT/health
# → {"status":"ready","model":"xtts_v2"}
```

### Síntesis de voz

```bash
curl -X POST http://IP:PORT/synthesize \
  -F "text=Hola, esto es una prueba del sistema de síntesis de voz." \
  -F "language=es" \
  -F "speaker_wav=@/ruta/a/tu/audio_referencia.wav" \
  --output output.wav
```

**Parámetros:**
- `text` — El texto a sintetizar (string)
- `language` — Código de idioma: `es`, `en`, `fr`, `de`, `it`, `pt`, `pl`, `tr`, `ru`, `nl`, `cs`, `ar`, `zh-cn`, `ja`, `hu`, `ko`
- `speaker_wav` — Archivo de audio con la voz de referencia (WAV o MP3, idealmente 1-2 minutos)

**Respuesta:** Archivo WAV con el audio sintetizado.

### Desde Python

```python
import requests

with open("referencia.wav", "rb") as f:
    response = requests.post(
        "http://IP:PORT/synthesize",
        data={
            "text": "Hola mundo, esto es una prueba.",
            "language": "es",
        },
        files={"speaker_wav": ("ref.wav", f, "audio/wav")},
    )

with open("output.wav", "wb") as f:
    f.write(response.content)
```

---

## Estructura del proyecto

```
pvc-tts/
├── .github/workflows/
│   ├── build-tts.yml       # Build y push de la imagen Docker
│   ├── start-tts.yml       # Arrancar instancia Vast.ai
│   └── stop-tts.yml        # Apagar instancia Vast.ai
├── tts/
│   ├── src/
│   │   ├── inference/
│   │   │   └── xtts_wrapper.py     # Wrapper del modelo XTTS v2
│   │   ├── streaming/
│   │   │   └── server.py           # Servidor FastAPI
│   │   └── watchdog/
│   │       └── watchdog.py         # Auto-apagado por inactividad
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── entrypoint.sh
│   └── requirements.txt
├── scripts/
│   └── vastai_control.py   # CLI para manejar la instancia
└── .env.example
```

## Notas importantes

- **Costo**: Una RTX 3090 en Vast.ai cuesta ~$0.20-0.40/hr. El watchdog asegura que no quede prendida sin uso.
- **Primera carga**: XTTS v2 tarda ~60 segundos en cargar en GPU la primera vez que arranca el container.
- **Audio de referencia**: Cuanto más largo y limpio sea el audio de referencia (sin ruido de fondo), mejor la calidad de clonación.
- **Puerto**: Vast.ai mapea el puerto interno (8000) a un puerto público aleatorio. El script muestra el puerto correcto al hacer `start` o `status`.
# xtts-mimiq
