"""Oído de Jarvis: convierte lo que dices en texto.

Motores disponibles (elige con JARVIS_STT_ENGINE):
- google:  gratis, muy bueno en español, necesita internet.
- whisper: corre en tu PC con faster-whisper (sin internet). Más lento en
           equipos sin GPU; instala `pip install faster-whisper`.

SpeechRecognition se encarga de lo difícil: detecta cuándo empiezas a hablar
y cuándo terminas (por el silencio) y nos entrega solo esa frase.
"""
from __future__ import annotations

import logging

import numpy as np
import speech_recognition as sr

from jarvis.config import Settings

log = logging.getLogger(__name__)


class SpeechToText:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8          # silencio que marca el fin de la frase
        self.recognizer.dynamic_energy_threshold = True
        self._whisper = None
        self._calibrated = False

    def listen(self) -> str | None:
        """Escucha una frase. Devuelve el texto, o None si no se oyó/entendió nada."""
        with sr.Microphone(sample_rate=16000) as source:
            if not self._calibrated:
                log.info("Calibrando el ruido ambiente...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self._calibrated = True
            log.info("Escuchando...")
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.settings.listen_timeout,
                    phrase_time_limit=self.settings.phrase_time_limit,
                )
            except sr.WaitTimeoutError:
                return None
        return self._transcribe(audio)

    def _transcribe(self, audio: sr.AudioData) -> str | None:
        if self.settings.stt_engine == "whisper":
            return self._transcribe_whisper(audio)
        try:
            return self.recognizer.recognize_google(audio, language=self.settings.language)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            log.error("Sin conexión con el reconocimiento de Google: %s", exc)
            return None

    def _transcribe_whisper(self, audio: sr.AudioData) -> str | None:
        if self._whisper is None:
            from faster_whisper import WhisperModel

            log.info("Cargando Whisper '%s' (solo la primera vez)...", self.settings.whisper_model)
            self._whisper = WhisperModel(self.settings.whisper_model, device="auto", compute_type="int8")
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(samples, language=self.settings.language.split("-")[0])
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text or None

