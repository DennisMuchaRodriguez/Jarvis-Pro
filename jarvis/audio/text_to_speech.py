"""Voz de Jarvis: convierte texto en audio y lo reproduce.

Usa edge-tts (voces neuronales de Microsoft, gratis, suenan muy naturales).
Si no hay internet, cae a pyttsx3, que usa las voces instaladas en Windows.
"""
from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
from pathlib import Path

from jarvis.config import Settings

log = logging.getLogger(__name__)


def clean_for_speech(text: str) -> str:
    """Quita símbolos de formato que sonarían raro al leerlos en voz alta."""
    text = re.sub(r"https?://\S+", "el enlace", text)
    text = re.sub(r"[*_#`>|~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    def __init__(self, settings: Settings) -> None:
        self.voice = settings.voice
        self._audio_file = Path(tempfile.gettempdir()) / "jarvis_voz.mp3"
        self._mixer_ready = False
        self._offline_engine = None

    def say(self, text: str) -> None:
        text = clean_for_speech(text)
        if not text:
            return
        print(f"Jarvis: {text}")
        try:
            self._say_neural(text)
        except Exception as exc:  # sin internet, voz no disponible, etc.
            log.warning("Voz neuronal no disponible (%s); usando voz local.", exc)
            self._say_offline(text)

    def _say_neural(self, text: str) -> None:
        import edge_tts
        import pygame

        if not self._mixer_ready:
            pygame.mixer.init()
            self._mixer_ready = True
        # Liberamos el archivo anterior antes de sobrescribirlo (Windows lo bloquea).
        pygame.mixer.music.unload()
        asyncio.run(edge_tts.Communicate(text, self.voice).save(str(self._audio_file)))
        pygame.mixer.music.load(str(self._audio_file))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

    def _say_offline(self, text: str) -> None:
        import pyttsx3

        if self._offline_engine is None:
            self._offline_engine = pyttsx3.init()
            for voice in self._offline_engine.getProperty("voices"):
                if "spanish" in voice.name.lower() or "es" in str(voice.languages).lower():
                    self._offline_engine.setProperty("voice", voice.id)
                    break
        self._offline_engine.say(text)
        self._offline_engine.runAndWait()

