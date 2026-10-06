"""Voz de Jarvis: convierte texto en audio y lo reproduce.

Usa edge-tts (voces neuronales de Microsoft, gratis, suenan muy naturales).
Si no hay internet, cae a pyttsx3, que usa las voces instaladas en Windows.

Para que Jarvis sea rápido, la voz trabaja en segundo plano como una cadena:

    say("Enseguida.") ─▶ [hilo 1: genera el audio] ─▶ [hilo 2: lo reproduce]
    say("Abriendo...") ─▶ (se genera mientras suena la frase anterior)

say() vuelve al instante, así que Jarvis puede ir ejecutando la orden
mientras habla. Antes de escucharte, el núcleo llama a wait() para que
Jarvis no se grabe a sí mismo. Las frases ya dichas se guardan en una
carpeta temporal y la próxima vez suenan sin esperar a internet.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import queue
import re
import tempfile
import threading
import time
from pathlib import Path

from jarvis.config import Settings

log = logging.getLogger(__name__)
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

CACHE_DIR = Path(tempfile.gettempdir()) / "jarvis_voz"
CACHE_DAYS = 7


def clean_for_speech(text: str) -> str:
    """Quita símbolos de formato que sonarían raro al leerlos en voz alta."""
    text = re.sub(r"https?://\S+", "el enlace", text)
    text = re.sub(r"[*_#`>|~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    def __init__(self, settings: Settings) -> None:
        self.voice = settings.voice
        self._texts: queue.Queue[str] = queue.Queue()
        self._audio: queue.Queue[tuple[str, Path | None]] = queue.Queue()
        self._pending = 0
        self._lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._offline_engine = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._prune_cache()
        threading.Thread(target=self._synth_loop, name="voz-generar", daemon=True).start()
        threading.Thread(target=self._play_loop, name="voz-reproducir", daemon=True).start()

    def say(self, text: str) -> None:
        """Encola una frase y vuelve al instante."""
        text = clean_for_speech(text)
        if not text:
            return
        print(f"Jarvis: {text}", flush=True)
        with self._lock:
            self._pending += 1
            self._idle.clear()
        self._texts.put(text)

    def wait(self) -> None:
        """Espera a que Jarvis termine de hablar."""
        self._idle.wait()

    # ---- hilo 1: texto → archivo de audio ---------------------------------
    def _synth_loop(self) -> None:
        while True:
            text = self._texts.get()
            try:
                path = self._synthesize(text)
            except Exception as exc:  # sin internet, voz no disponible...
                log.warning("Voz neuronal no disponible (%s); usando voz local.", exc)
                path = None
            self._audio.put((text, path))

    def _synthesize(self, text: str) -> Path:
        import edge_tts

        path = CACHE_DIR / (hashlib.sha1(f"{self.voice}|{text}".encode()).hexdigest() + ".mp3")
        if path.exists() and path.stat().st_size > 0:
            return path  # ya la dijo antes: no hace falta internet
        tmp = path.with_suffix(".tmp")
        asyncio.run(edge_tts.Communicate(text, self.voice).save(str(tmp)))
        tmp.replace(path)
        return path

    # ---- hilo 2: reproducir en orden ---------------------------------------
    def _play_loop(self) -> None:
        while True:
            text, path = self._audio.get()
            try:
                if path is not None:
                    self._play_file(path)
                else:
                    self._say_offline(text)
            except Exception:
                log.exception("No pude reproducir la voz")
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending == 0:
                        self._idle.set()

    def _play_file(self, path: Path) -> None:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.03)
        pygame.mixer.music.unload()  # libera el archivo (Windows lo bloquea mientras está cargado)

    def _say_offline(self, text: str) -> None:
        if self._offline_engine is None:
            try:  # pyttsx3 usa COM en Windows, y este hilo debe inicializarlo
                import pythoncom

                pythoncom.CoInitialize()
            except ImportError:
                pass
            import pyttsx3

            self._offline_engine = pyttsx3.init()
            for voice in self._offline_engine.getProperty("voices"):
                if "spanish" in voice.name.lower() or "es" in str(voice.languages).lower():
                    self._offline_engine.setProperty("voice", voice.id)
                    break
        self._offline_engine.say(text)
        self._offline_engine.runAndWait()

    def _prune_cache(self) -> None:
        limit = time.time() - CACHE_DAYS * 86400
        for file in CACHE_DIR.glob("*.mp3"):
            try:
                if file.stat().st_atime < limit:
                    file.unlink()
            except OSError:
                pass
