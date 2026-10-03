"""Oído de Jarvis: convierte lo que dices en texto.

Dos pasos:
  1. recorder.PhraseRecorder graba tu frase COMPLETA (detecta voz, no volumen).
  2. Un motor la transcribe (elige con JARVIS_STT_ENGINE):
     - google:  gratis, muy bueno en español, necesita internet.
     - whisper: corre en tu PC con faster-whisper (sin internet). Más lento en
                equipos sin GPU; instala `pip install faster-whisper`.
"""
from __future__ import annotations

import logging

import numpy as np

from jarvis.audio.recorder import SAMPLE_RATE, PhraseRecorder
from jarvis.config import Settings

log = logging.getLogger(__name__)


class SpeechToText:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.recorder = PhraseRecorder(
            device=settings.mic_device,
            vad_aggressiveness=settings.vad_aggressiveness,
            silence_end=settings.silence_end,
            max_phrase=settings.phrase_time_limit,
            max_gain=settings.mic_max_gain,
            beep=settings.listen_beep,
        )
        self._whisper = None

    def listen(self) -> str | None:
        """Escucha una frase. Devuelve el texto, o None si no se oyó/entendió nada."""
        samples = self.recorder.record(timeout=self.settings.listen_timeout)
        if samples is None:
            return None
        return self.transcribe(samples)

    def transcribe(self, samples: np.ndarray) -> str | None:
        if self.settings.stt_engine == "whisper":
            return self._transcribe_whisper(samples)
        return self._transcribe_google(samples)

    def _transcribe_google(self, samples: np.ndarray) -> str | None:
        import speech_recognition as sr

        audio = sr.AudioData(samples.tobytes(), SAMPLE_RATE, 2)
        try:
            return sr.Recognizer().recognize_google(audio, language=self.settings.language)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            log.error("Sin conexión con el reconocimiento de Google: %s", exc)
            return None

    def _transcribe_whisper(self, samples: np.ndarray) -> str | None:
        if self._whisper is None:
            from faster_whisper import WhisperModel

            log.info("Cargando Whisper '%s' (solo la primera vez)...", self.settings.whisper_model)
            self._whisper = WhisperModel(self.settings.whisper_model, device="auto", compute_type="int8")
        audio = samples.astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(audio, language=self.settings.language.split("-")[0])
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text or None
