import torch
import numpy as np
import io
import wave
from pathlib import Path
import glob
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

matches = glob.glob("/app/model/**/config.json", recursive=True)
MODEL_DIR = Path(matches[0]).parent if matches else Path("/app/model")

class XTTSWrapper:
    def __init__(self):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[XTTS] Using device: {self.device}")

    def load(self):
        print("[XTTS] Loading model...")
        config = XttsConfig()
        config.load_json(str(MODEL_DIR / "config.json"))

        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(
            config,
            checkpoint_dir=str(MODEL_DIR),
            eval=True,
        )
        self.model.to(self.device)
        print("[XTTS] Model ready.")

    def generate(self, text: str, speaker_wav_path: str, language: str = "es") -> bytes:
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[speaker_wav_path],
            gpt_cond_len=30,
            max_ref_length=60,
        )

        outputs = self.model.inference(
            text=text,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
            length_penalty=1.0,
            repetition_penalty=10.0,
            top_k=50,
            top_p=0.85,
        )

        wav_array = outputs["wav"]
        
        # Debug: ver qué devuelve el modelo
        print(f"[XTTS] wav_array type: {type(wav_array)}")
        print(f"[XTTS] wav_array shape: {wav_array.shape if hasattr(wav_array, 'shape') else 'no shape'}")
        print(f"[XTTS] wav_array dtype: {wav_array.dtype if hasattr(wav_array, 'dtype') else 'unknown'}")
        print(f"[XTTS] wav_array min/max: {wav_array.min():.4f} / {wav_array.max():.4f}")
        duration = len(wav_array) / 24000
        print(f"[XTTS] Expected duration: {duration:.2f}s")

        if hasattr(wav_array, 'cpu'):
            wav_array = wav_array.cpu().numpy()

        return self._to_ogg_bytes(wav_array, sample_rate=24000)
    
    def _to_ogg_bytes(self, wav_array: np.ndarray, sample_rate: int) -> bytes:
        """Convierte numpy float32 array a bytes OGG Vorbis."""
        buffer = io.BytesIO()
        sf.write(buffer, wav_array, sample_rate, format="OGG", subtype="VORBIS")
        buffer.seek(0)
        return buffer.read()

    def generate_streaming(self, text: str, speaker_wav_path: str, language: str = "es"):
        """
        Genera audio por frases y las yields como bytes WAV individuales.
        Util para streaming real: el cliente puede empezar a reproducir antes
        de que termine la generacion completa.
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[speaker_wav_path],
            gpt_cond_len=30,
            max_ref_length=60,
        )

        # inference_stream genera chunk por chunk (por frase interna)
        chunks = self.model.inference_stream(
            text=text,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
        )

        for chunk in chunks:
            # chunk es un tensor, lo convertimos a bytes raw PCM int16
            chunk_np = chunk.cpu().numpy()
            audio_int16 = (chunk_np * 32767).astype(np.int16)
            yield audio_int16.tobytes()

    def _to_wav_bytes(self, wav_array: np.ndarray, sample_rate: int) -> bytes:
        """Convierte numpy float32 array a bytes de archivo WAV."""
        audio_int16 = (wav_array * 32767).astype(np.int16)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)       # mono
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())
        return buffer.getvalue()
