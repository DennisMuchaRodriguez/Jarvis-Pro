"""Configuración central: lee el archivo .env y la expone como un objeto Settings.

Todo lo que quieras ajustar sin tocar código (voz, idioma, modelo, sensibilidad
de los aplausos...) vive en .env. Mira .env.example para ver cada opción.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

load_dotenv(ROOT_DIR / ".env")


def _str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "si", "sí", "yes")


@dataclass(frozen=True)
class Settings:
    # Cerebro
    model: str
    effort: str
    web_search: bool
    # Personalidad
    user_name: str
    user_title: str
    # Oído y voz
    language: str
    stt_engine: str
    whisper_model: str
    voice: str
    listen_timeout: float
    phrase_time_limit: float
    silence_end: float
    vad_aggressiveness: int
    mic_device: str
    mic_max_gain: float
    listen_beep: bool
    idle_rounds: int
    # Aplausos
    clap_threshold: float
    clap_min_gap: float
    clap_max_gap: float
    # Programas
    unity_editor_path: str
    whatsapp_mode: str
    discord_open_wait: float


def load_settings() -> Settings:
    return Settings(
        model=_str("JARVIS_MODEL", "claude-opus-5-5"),
        effort=_str("JARVIS_EFFORT", "low"),
        web_search=_bool("JARVIS_WEB_SEARCH", True),
        user_name=_str("JARVIS_USER_NAME", "Dennis"),
        user_title=_str("JARVIS_USER_TITLE", "señor"),
        language=_str("JARVIS_LANGUAGE", "es-MX"),
        stt_engine=_str("JARVIS_STT_ENGINE", "google"),
        whisper_model=_str("JARVIS_WHISPER_MODEL", "small"),
        voice=_str("JARVIS_VOICE", "es-MX-JorgeNeural"),
        listen_timeout=_float("JARVIS_LISTEN_TIMEOUT", 8),
        phrase_time_limit=_float("JARVIS_PHRASE_TIME_LIMIT", 20),
        silence_end=_float("JARVIS_SILENCE_END", 1.2),
        vad_aggressiveness=_int("JARVIS_VAD_MODE", 1),
        mic_device=_str("JARVIS_MIC_DEVICE", ""),
        mic_max_gain=_float("JARVIS_MIC_MAX_GAIN", 8),
        listen_beep=_bool("JARVIS_LISTEN_BEEP", True),
        idle_rounds=_int("JARVIS_IDLE_ROUNDS", 2),
        clap_threshold=_float("JARVIS_CLAP_THRESHOLD", 0.30),
        clap_min_gap=_float("JARVIS_CLAP_MIN_GAP", 0.12),
        clap_max_gap=_float("JARVIS_CLAP_MAX_GAP", 0.80),
        unity_editor_path=_str("UNITY_EDITOR_PATH", ""),
        whatsapp_mode=_str("WHATSAPP_MODE", "desktop"),
        discord_open_wait=_float("DISCORD_OPEN_WAIT", 15),
    )
