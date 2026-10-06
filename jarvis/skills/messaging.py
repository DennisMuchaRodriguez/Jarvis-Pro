"""Enviar mensajes por WhatsApp. Contactos en data/contacts.json.

Cómo funciona: abrimos un enlace especial de WhatsApp que ya trae el número
y el texto escrito, esperamos a que cargue y pulsamos Enter. Requiere que la
sesión de WhatsApp (Desktop o Web) ya esté iniciada.
"""
from __future__ import annotations

import time
import webbrowser
from urllib.parse import quote

from jarvis.config import load_settings
from jarvis.skills._helpers import find_entry, load_data, open_target, press_keys
from jarvis.skills.registry import registry

CONTACTS = load_data("contacts.json")
_KNOWN = ", ".join(CONTACTS) or "(ninguno configurado)"


def find_contact(name: str) -> tuple[str, dict] | None:
    return find_entry(name, CONTACTS)


@registry.tool(
    name="send_whatsapp",
    quick=True,
    description=f"Envía un mensaje de WhatsApp a un contacto. Contactos: {_KNOWN}.",
    parameters={
        "contact": {"type": "string", "description": "Nombre del contacto."},
        "message": {"type": "string", "description": "Texto exacto del mensaje."},
    },
    confirm="¿Envío a {contact} el mensaje: {message}?",
)
def send_whatsapp(contact: str, message: str) -> str:
    match = find_contact(contact)
    if not match:
        return f"No tengo a '{contact}' en contactos. Contactos: {_KNOWN}."
    key, entry = match
    phone = entry["phone"].replace("+", "").replace(" ", "")

    if load_settings().whatsapp_mode == "web":
        webbrowser.open(f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}")
        time.sleep(15)  # WhatsApp Web tarda en cargar
    else:
        open_target(f"whatsapp://send?phone={phone}&text={quote(message)}")
        time.sleep(4)
    press_keys("enter")
    return f"Mensaje enviado a {key}."
