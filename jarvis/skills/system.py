"""Control del sistema: volumen, multimedia, escribir, capturas, energía, hora."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from jarvis.skills._helpers import IS_MAC, IS_WINDOWS, paste_text, press_keys
from jarvis.skills.registry import registry

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@registry.tool(
    name="get_datetime",
    description="Devuelve la fecha y la hora actuales.",
)
def get_datetime() -> str:
    now = datetime.now()
    return f"{DAYS[now.weekday()]} {now.day} de {MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}"


@registry.tool(
    name="set_volume",
    description="Sube, baja o silencia el volumen del sistema.",
    parameters={
        "action": {"type": "string", "enum": ["up", "down", "mute"]},
        "steps": {"type": "integer", "description": "Cuánto subir/bajar (cada paso ≈ 2%). Usa 5 si no lo dicen."},
    },
)
def set_volume(action: str, steps: int) -> str:
    key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}[action]
    press_keys(key, presses=1 if action == "mute" else max(1, min(steps, 50)))
    return "Hecho."


@registry.tool(
    name="media_control",
    description="Controla la música o video que se esté reproduciendo (Spotify, YouTube, etc.).",
    parameters={"action": {"type": "string", "enum": ["play_pause", "next", "previous"]}},
)
def media_control(action: str) -> str:
    press_keys({"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack"}[action])
    return "Hecho."


@registry.tool(
    name="type_text",
    description="Escribe un texto donde esté el cursor (dictado). Útil para escribir en cualquier programa.",
    parameters={"text": {"type": "string"}},
)
def type_text(text: str) -> str:
    paste_text(text)
    return "Texto escrito."


@registry.tool(
    name="take_screenshot",
    description="Toma una captura de pantalla y la guarda en Imágenes/Jarvis.",
)
def take_screenshot() -> str:
    import pyautogui

    folder = Path.home() / "Pictures" / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"captura_{datetime.now():%Y%m%d_%H%M%S}.png"
    pyautogui.screenshot(str(path))
    return f"Captura guardada en {path}."


@registry.tool(
    name="system_status",
    description="Informa del uso de CPU, memoria RAM y batería.",
)
def system_status() -> str:
    import psutil

    parts = [f"CPU al {psutil.cpu_percent(interval=0.5):.0f}%",
             f"RAM al {psutil.virtual_memory().percent:.0f}%"]
    battery = psutil.sensors_battery()
    if battery:
        plugged = "cargando" if battery.power_plugged else "sin cargador"
        parts.append(f"batería al {battery.percent:.0f}% ({plugged})")
    return ", ".join(parts)


@registry.tool(
    name="lock_pc",
    description="Bloquea la sesión del PC.",
)
def lock_pc() -> str:
    if IS_WINDOWS:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif IS_MAC:
        subprocess.Popen(["pmset", "displaysleepnow"])
    else:
        subprocess.Popen(["loginctl", "lock-session"])
    return "PC bloqueado."


@registry.tool(
    name="power",
    description="Apaga o reinicia el PC.",
    parameters={"action": {"type": "string", "enum": ["apagar", "reiniciar"]}},
    confirm="¿Confirma que desea {action} el equipo?",
)
def power(action: str) -> str:
    shutdown = action == "apagar"
    if IS_WINDOWS:
        subprocess.Popen(["shutdown", "/s" if shutdown else "/r", "/t", "10"])
    else:
        subprocess.Popen(["shutdown", "-h" if shutdown else "-r", "+1"])
    return "El equipo se apagará en unos segundos." if shutdown else "Reiniciando en unos segundos."
