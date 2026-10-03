"""Enviar mensajes por Discord. Destinos en data/discord.json.

Dos formas de enviar, según cómo configures cada destino:

1. App de Discord (por defecto): Jarvis abre Discord, usa el buscador rápido
   (Ctrl+K), escribe el nombre del amigo o canal, pulsa Enter, pega el mensaje
   y lo envía. El mensaje sale DESDE TU CUENTA, a amigos, grupos o canales.
   Requiere tener la app de Discord abierta con tu sesión iniciada, y no tocar
   el teclado mientras lo hace (unos segundos).

2. Webhook: para canales de servidores donde tengas permiso de "Gestionar
   webhooks". No necesita abrir nada y es 100% fiable, pero el mensaje sale
   con el nombre "Jarvis", no con el tuyo. Cómo crear uno: Ajustes del
   servidor → Integraciones → Webhooks → Nuevo webhook → elige el canal →
   "Copiar URL del webhook", y pégala en data/discord.json.

Si dices un nombre que no está en discord.json, Jarvis lo busca igualmente
con Ctrl+K usando ese nombre.
"""
from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from jarvis.config import load_settings
from jarvis.skills._helpers import IS_MAC, find_entry, load_data, open_target, paste_text, press_keys
from jarvis.skills.registry import registry

DESTINATIONS = load_data("discord.json")
_KNOWN = ", ".join(DESTINATIONS) or "(ninguno configurado)"


def send_webhook(url: str, message: str) -> None:
    body = json.dumps({"content": message, "username": "Jarvis"}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": "Jarvis-Pro (https://github.com, 1.0)",  # Discord rechaza peticiones sin User-Agent
    })
    urlopen(request, timeout=10).close()


def discord_is_running() -> bool:
    import psutil

    return any((p.info["name"] or "").lower().startswith("discord") for p in psutil.process_iter(["name"]))


def send_with_app(search: str, message: str) -> None:
    was_running = discord_is_running()
    open_target("discord://")  # abre Discord o lo trae al frente
    time.sleep(2.5 if was_running else load_settings().discord_open_wait)

    press_keys("command" if IS_MAC else "ctrl", "k")  # buscador rápido de Discord
    time.sleep(0.6)
    paste_text(search)
    time.sleep(1.2)          # esperamos a que aparezcan los resultados
    press_keys("enter")
    time.sleep(1.5)          # se abre el chat y el cursor queda en la caja de mensaje
    paste_text(message)
    time.sleep(0.3)
    press_keys("enter")


@registry.tool(
    name="send_discord",
    description=(
        "Envía un mensaje por Discord a un amigo, grupo o canal. Destinos configurados: "
        f"{_KNOWN}. Si piden otro nombre, úsalo tal cual: se buscará en Discord."
    ),
    parameters={
        "destination": {"type": "string", "description": "Amigo, grupo o canal de destino."},
        "message": {"type": "string", "description": "Texto exacto del mensaje."},
    },
    confirm="¿Envío por Discord a {destination} el mensaje: {message}?",
)
def send_discord(destination: str, message: str) -> str:
    match = find_entry(destination, DESTINATIONS)
    name, entry = match if match else (destination, {})

    if entry.get("webhook"):
        send_webhook(entry["webhook"], message)
        return f"Mensaje publicado en {name} con el webhook."

    send_with_app(entry.get("search", name), message)
    return (f"Mensaje enviado a {name} desde la app de Discord. "
            "Si el buscador eligió a otra persona, sugiere añadirla a data/discord.json.")
