"""Utilidades compartidas por las habilidades: abrir cosas y buscar nombres parecidos."""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from jarvis.config import DATA_DIR

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def normalize(text: str) -> str:
    """'Visual Studio Códe ' -> 'visual studio code' (sin acentos ni mayúsculas)."""
    text = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in text if not unicodedata.combining(c))


def load_data(filename: str) -> dict[str, dict]:
    """Carga un JSON de la carpeta data/ ignorando las claves que empiezan por '_' (comentarios)."""
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}


def find_entry(query: str, entries: dict[str, dict]) -> tuple[str, dict] | None:
    """Busca `query` entre los nombres y alias de `entries`, tolerando errores del reconocimiento de voz."""
    names: dict[str, str] = {}
    for key, entry in entries.items():
        names[normalize(key)] = key
        for alias in entry.get("aliases", []):
            names[normalize(alias)] = key

    q = normalize(query)
    if q in names:
        key = names[q]
        return key, entries[key]
    for name, key in names.items():
        # Coincidencia parcial ("abre counter" → "counter strike 2"); ignoramos alias muy cortos como "cs".
        if len(q) >= 4 and len(name) >= 4 and (q in name or name in q):
            return key, entries[key]
    close = difflib.get_close_matches(q, list(names), n=1, cutoff=0.7)
    if close:
        key = names[close[0]]
        return key, entries[key]
    return None


def open_target(target: str, args: list[str] | None = None) -> None:
    """Abre un programa, archivo, carpeta o URI (steam://, spotify:, https://...)."""
    if args:
        executable = shutil.which(target) or target
        subprocess.Popen([executable, *args])
    elif IS_WINDOWS:
        os.startfile(target)  # type: ignore[attr-defined]  # igual que doble clic / Win+R
    elif IS_MAC:
        subprocess.Popen(["open", target])
    elif "://" in target or target.endswith(":") or Path(target).exists():
        subprocess.Popen(["xdg-open", target])
    else:
        subprocess.Popen([target])


def press_keys(*keys: str, presses: int = 1) -> None:
    import pyautogui

    if len(keys) == 1:
        pyautogui.press(keys[0], presses=presses, interval=0.02)
    else:
        pyautogui.hotkey(*keys)


def paste_text(text: str) -> None:
    """Escribe `text` donde esté el cursor. Usa el portapapeles porque pyautogui no escribe acentos ni ñ."""
    import pyperclip

    pyperclip.copy(text)
    press_keys("command" if IS_MAC else "ctrl", "v")
