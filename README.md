# TTS Voice Cloning Service

Servicio de clonación de voz self-hosted basado en [XTTS v2](https://huggingface.co/coqui/XTTS-v2). Recibe un texto y un audio de referencia, y devuelve un archivo de audio con el texto leído en la voz del audio de referencia. La inferencia corre en una GPU on-demand de [Vast.ai](https://vast.ai), lo que significa que solo pagás cuando lo usás.

## ¿Cómo funciona?

XTTS v2 es un modelo de text-to-speech con zero-shot voice cloning: no necesita entrenamiento previo con la voz objetivo. Alcanza con proveer un audio de referencia de 1-2 minutos para que el modelo pueda replicar esa voz al sintetizar cualquier texto.

La infraestructura está diseñada para ser económica: la instancia GPU se crea cuando se necesita y se destruye automáticamente tras 30 minutos de inactividad, evitando costos innecesarios.

```
Cliente (curl / aplicación)
        │
        │  POST /synthesize
        │  { texto + audio de referencia }
        ▼
  Vast.ai GPU instance
  └── Docker container
      ├── FastAPI server      ← recibe la request HTTP
      ├── XTTS v2 (en GPU)   ← sintetiza el audio
      └── Watchdog           ← apaga la instancia tras inactividad
```

## Requisitos previos

Antes de empezar necesitás cuentas en tres servicios, todos con tier gratuito disponible:

- **[GitHub](https://github.com)** — para alojar el repo y correr los workflows de CI/CD
- **[Docker Hub](https://hub.docker.com)** — para publicar la imagen Docker del servicio
- **[Vast.ai](https://vast.ai)** — para alquilar la GPU donde corre el modelo (se paga por hora de uso)

## Setup

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/tts-voice-cloning
cd tts-voice-cloning
```

### 2. Obtener las credenciales necesarias

**Vast.ai API Key**
Ir a [console.vast.ai/account](https://console.vast.ai/account) → sección *API Keys* → crear una nueva key.

**Docker Hub Token**
Ir a [hub.docker.com](https://hub.docker.com) → Account Settings → Security → New Access Token. Guardar el token, solo se muestra una vez.

### 3. Configurar los secrets en GitHub

En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Cómo obtenerlo |
|--------|----------------|
| `VAST_API_KEY` | Vast.ai → Account → API Keys |
| `DOCKERHUB_USERNAME` | Tu nombre de usuario de Docker Hub |
| `DOCKERHUB_TOKEN` | Docker Hub → Account Settings → Security → Access Token |

Los siguientes son opcionales y solo necesarios si querés integrar un backend propio que actúe de proxy entre tu frontend y este servicio:

| Secret | Descripción |
|--------|-------------|
| `BACKEND_URL` | URL de tu backend (ej: `https://api.miapp.com`) |
| `INTERNAL_SECRET` | Clave compartida para autenticar la comunicación entre servicios |

### 4. Configurar las variables de entorno locales

```bash
cp .env.example .env
```

Abrir `.env` y completar los valores con las mismas credenciales del paso anterior. Estas variables son las que usa el script de control desde la terminal.

### 5. Construir y publicar la imagen Docker

Ir a **Actions → Build & Push TTS Image → Run workflow**.

Este paso construye la imagen Docker que incluye el modelo XTTS v2 pre-descargado (~2 GB) y la publica en Docker Hub. El modelo va dentro de la imagen para que cuando Vast.ai levante el container, no tenga que descargarlo en cada arranque.

> La primera vez tarda alrededor de 15 minutos. Los builds siguientes son más rápidos gracias al cache de capas de Docker.

Solo es necesario repetir este paso si se modifica el código del servicio (`tts/`). Un push a `main` con cambios en esa carpeta lo dispara automáticamente.

---

## Uso

### Prender la instancia GPU

**Desde GitHub Actions**:

Ir a **Actions → Start TTS Instance → Run workflow**. Se puede elegir el tipo de GPU en el menú desplegable (RTX 3090 por defecto).

**Desde la terminal:**

```bash
source .env
python scripts/vastai_control.py start
```

El script busca automáticamente la oferta más barata disponible que cumpla los requisitos mínimos, crea la instancia, y espera hasta confirmar que está corriendo. El proceso tarda entre 3 y 5 minutos (boot del sistema + carga del modelo en GPU).

Al terminar, muestra la URL de conexión:

```
Connection:
  IP:   123.45.67.89
  Port: 12345
  URL:  http://123.45.67.89:12345
```

### Ver el estado de la instancia

```bash
python scripts/vastai_control.py status
```

### Apagar la instancia

**Desde GitHub Actions:** Actions → Stop TTS Instance → Run workflow

**Desde la terminal:**

```bash
python scripts/vastai_control.py stop
```

La instancia también se apaga **automáticamente** tras 30 minutos sin recibir requests (comportamiento del watchdog). Este tiempo es configurable con la variable `WATCHDOG_TIMEOUT_SECONDS` en el `.env`.

---

## API

### `GET /health`

Verifica que el servicio está listo para recibir requests.

```bash
curl http://IP:PORT/health
```

```json
{"status": "ready", "model": "xtts_v2"}
```

### `POST /synthesize`

Sintetiza un texto con la voz del audio de referencia y devuelve un archivo WAV.

**Parámetros (form-data):**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `text` | string | ✅ | Texto a sintetizar |
| `speaker_wav` | archivo | ✅ | Audio de referencia en WAV o MP3 (idealmente 1-2 minutos, sin ruido de fondo) |
| `language` | string | No | Código de idioma del texto. Default: `es` |

**Idiomas soportados:** `es`, `en`, `fr`, `de`, `it`, `pt`, `pl`, `tr`, `ru`, `nl`, `cs`, `ar`, `zh-cn`, `ja`, `hu`, `ko`

**Respuesta:** Archivo `audio/wav` con el texto sintetizado en la voz del audio de referencia.

**Ejemplo con curl:**

```bash
curl -X POST http://IP:PORT/synthesize \
  -F "text=El rápido zorro marrón salta sobre el perro perezoso." \
  -F "language=es" \
  -F "speaker_wav=@referencia.wav" \
  --output output.wav
```

**Ejemplo con Python:**

```python
import requests

url = "http://IP:PORT/synthesize"

with open("referencia.wav", "rb") as audio_file:
    response = requests.post(
        url,
        data={
            "text": "El rápido zorro marrón salta sobre el perro perezoso.",
            "language": "es",
        },
        files={
            "speaker_wav": ("referencia.wav", audio_file, "audio/wav")
        },
    )

response.raise_for_status()

with open("output.wav", "wb") as output_file:
    output_file.write(response.content)

print("Audio guardado en output.wav")
```

---

## Estructura del proyecto

```
tts-voice-cloning/
├── .github/workflows/
│   ├── build-tts.yml       # Construye y publica la imagen Docker
│   ├── start-tts.yml       # Crea la instancia GPU en Vast.ai
│   └── stop-tts.yml        # Destruye la instancia GPU
├── tts/
│   ├── src/
│   │   ├── inference/
│   │   │   └── xtts_wrapper.py     # Carga el modelo y genera el audio
│   │   ├── streaming/
│   │   │   └── server.py           # Servidor FastAPI con el endpoint /synthesize
│   │   └── watchdog/
│   │       └── watchdog.py         # Auto-apagado por inactividad
│   ├── docker/
│   │   ├── Dockerfile              # Imagen base CUDA + dependencias + modelo
│   │   └── entrypoint.sh           # Obtiene la IP pública e inicia el servidor
│   └── requirements.txt
├── scripts/
│   └── vastai_control.py   # CLI: start / stop / status de la instancia
├── .env.example            # Plantilla de variables de entorno
└── README.md
```

---

## Consideraciones

**Costo:** Una RTX 3090 en Vast.ai cuesta aproximadamente $0.20–$0.40/hr dependiendo de la oferta. El watchdog garantiza que la instancia no quede corriendo sin uso. Vast.ai cobra solo por el tiempo que la instancia está activa.

**Calidad del audio de referencia:** El resultado de la clonación depende directamente de la calidad del audio de referencia. Un audio grabado en ambiente silencioso, sin música de fondo, y de al menos 60 segundos produce resultados notablemente mejores que un clip corto o con ruido.

**Puerto dinámico:** Vast.ai asigna un puerto público aleatorio en cada instancia. El script `vastai_control.py` lo detecta automáticamente y lo muestra al hacer `start` o `status`. Si integrás este servicio en un sistema más grande, el endpoint cambia con cada instancia — considerá guardar la URL dinámicamente (por ejemplo en una base de datos o secret manager) para que otros servicios puedan leerla.

**Tiempo de arranque:** El primer request después de iniciar la instancia puede tardar hasta 60–90 segundos mientras XTTS v2 termina de cargarse en GPU. Los requests siguientes son inmediatos.
