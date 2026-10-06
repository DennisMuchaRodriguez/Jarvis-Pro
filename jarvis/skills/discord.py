"""Discord: enviar mensajes (amigos, grupos, canales de servidores) y mutearte/ensordecerte.

Formas de enviar, según cómo configures cada destino en data/discord.json:

1. "link" (canales concretos de un servidor, o un chat concreto): el enlace
   del canal. Jarvis lo abre directamente en la app, pega el mensaje y lo
   envía desde TU cuenta. Es la forma más exacta para servidores.
   Cómo obtenerlo: en Discord, clic derecho sobre el canal → "Copiar enlace".
   Queda así: https://discord.com/channels/111111111111/222222222222

2. "search" (amigos y grupos): Jarvis abre el buscador rápido (Ctrl+K),
   escribe ese texto y pulsa Enter. También desde tu cuenta. Prefijos útiles
   del buscador: @usuario, #canal, *servidor.

3. "webhook" (canales donde tengas permiso de "Gestionar webhooks"): no
   necesita la app y es 100% fiable, pero el mensaje sale firmado "Jarvis".
   Ajustes del servidor → Integraciones → Webhooks → Nuevo → Copiar URL.

Si dices un nombre que no está en discord.json, Jarvis lo busca con Ctrl+K.
Con las formas 1 y 2 no toques el teclado durante esos segundos.

Mutear/ensordecer: lo más cómodo es crear atajos GLOBALES en Discord
(Ajustes → Atajos de teclado → "Alternar silencio" / "Alternar ensordecer")
y ponerlos en .env (DISCORD_MUTE_HOTKEY / DISCORD_DEAFEN_HOTKEY). Así funcionan
aunque estés en un juego. Sin ellos, Jarvis trae Discord al frente y usa
Ctrl+Shift+M / Ctrl+Shift+D.
"""
from __future__ import annotations

import json
import re
import time
from urllib.request import Request, urlopen

from jarvis.config import load_settings
from jarvis.skills._helpers import IS_MAC, find_entry, load_data, open_target, paste_text, press_keys
from jarvis.skills.registry import registry

DESTINATIONS = load_data("discord.json")
_KNOWN = ", ".join(DESTINATIONS) or "(ninguno configurado)"
_CHANNEL_LINK = re.compile(r"discord(?:app)?\.com/channels/(@me|\d+)/(\d+)")


def send_webhook(url: str, message: str) -> None:
    body = json.dumps({"content": message, "username": "Jarvis"}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": "Jarvis-Pro (https://github.com, 1.0)",  # Discord rechaza peticiones sin User-Agent
    })
    urlopen(request, timeout=10).close()


def app_link(link: str) -> str:
    """https://discord.com/channels/G/C → discord://-/channels/G/C (lo abre la app, no el navegador)."""
    match = _CHANNEL_LINK.search(link)
    if not match:
        raise ValueError(f"No reconozco el enlace de Discord: {link}")
    return f"discord://-/channels/{match.group(1)}/{match.group(2)}"


def discord_is_running() -> bool:
    import psutil

    return any((p.info["name"] or "").lower().startswith("discord") for p in psutil.process_iter(["name"]))


def bring_discord(target: str = "discord://") -> None:
    """Abre Discord (o un canal) y espera a que esté al frente."""
    was_running = discord_is_running()
    open_target(target)
    time.sleep(2.5 if was_running else load_settings().discord_open_wait)


def _ctrl() -> str:
    return "command" if IS_MAC else "ctrl"


def send_with_app(search: str, message: str) -> None:
    bring_discord()
    press_keys(_ctrl(), "k")  # buscador rápido de Discord
    time.sleep(0.6)
    paste_text(search)
    time.sleep(1.2)           # esperamos a que aparezcan los resultados
    press_keys("enter")
    time.sleep(1.5)           # se abre el chat y el cursor queda en la caja de mensaje
    paste_text(message)
    time.sleep(0.3)
    press_keys("enter")


def send_with_link(link: str, message: str) -> None:
    bring_discord(app_link(link))
    time.sleep(1.0)           # al cambiar de canal, Discord pone el cursor en la caja de mensaje
    paste_text(message)
    time.sleep(0.3)
    press_keys("enter")


@registry.tool(
    name="send_discord",
    quick=True,
    description=(
        "Envía un mensaje por Discord a un amigo, grupo o canal de un servidor. Destinos configurados: "
        f"{_KNOWN}. Si piden otro destino, escríbelo para el buscador de Discord: '@usuario' para "
        "una persona, '#nombre-del-canal' para un canal, o el nombre del grupo tal cual."
    ),
    parameters={
        "destination": {"type": "string", "description": "Destino configurado o texto para el buscador."},
        "message": {"type": "string", "description": "Texto exacto del mensaje."},
    },
    confirm=lambda destination, message: f"¿Envío por Discord a {destination.lstrip('@#*')} el mensaje: {message}?",
)
def send_discord(destination: str, message: str) -> str:
    match = find_entry(destination.lstrip("@#*"), DESTINATIONS)
    name, entry = match if match else (destination.lstrip("@#*"), {})

    if entry.get("webhook"):
        send_webhook(entry["webhook"], message)
    elif entry.get("link"):
        send_with_link(entry["link"], message)
    else:
        send_with_app(entry.get("search", destination), message)
    return f"Mensaje enviado a {name} por Discord."


def parse_hotkey(hotkey: str) -> list[str]:
    """'Ctrl + Shift + F9' → ['ctrl', 'shift', 'f9']"""
    return [key.strip().lower() for key in hotkey.split("+") if key.strip()]


@registry.tool(
    name="discord_voice",
    quick=True,
    description=(
        "Alterna el micrófono (mute) o el audio (ensordecer / deafen) del usuario en Discord. "
        "Es un interruptor: si ya estaba silenciado, lo vuelve a activar."
    ),
    parameters={"action": {"type": "string", "enum": ["mute", "deafen"]}},
)
def discord_voice(action: str) -> str:
    settings = load_settings()
    hotkey = settings.discord_mute_hotkey if action == "mute" else settings.discord_deafen_hotkey
    if hotkey:
        press_keys(*parse_hotkey(hotkey))  # atajo global: no hace falta traer Discord al frente
    else:
        bring_discord()
        press_keys(_ctrl(), "shift", "m" if action == "mute" else "d")
    return "Micrófono de Discord alternado." if action == "mute" else "Audio de Discord alternado."
