"""Mensajes programados: Jarvis los envía solo a la hora indicada."""
from __future__ import annotations

from datetime import datetime

from jarvis.config import PRIVATE_DIR
from jarvis.services.scheduler import Scheduler, spoken_time
from jarvis.skills import discord, messaging
from jarvis.skills.registry import registry

SCHEDULER = Scheduler(
    PRIVATE_DIR / "programados.json",
    senders={"whatsapp": messaging.send_whatsapp, "discord": discord.send_discord},
)


def parse_time(send_at: str, now: datetime | None = None) -> datetime:
    """Acepta 'AAAA-MM-DD HH:MM' o solo 'HH:MM' (hoy, o mañana si esa hora ya pasó)."""
    now = now or datetime.now()
    text = send_at.strip().replace("T", " ")
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        clock = datetime.strptime(text, "%H:%M").time()
        when = datetime.combine(now.date(), clock)
        return when if when > now else datetime.combine(now.date().fromordinal(now.toordinal() + 1), clock)


def _confirm_question(platform: str, destination: str, message: str, send_at: str) -> str:
    try:
        moment = spoken_time(parse_time(send_at))
    except ValueError:
        moment = send_at
    return f"¿Programo para {moment} un mensaje por {platform} a {destination} que diga: {message}?"


@registry.tool(
    name="schedule_message",
    quick=True,
    description=(
        "Programa un mensaje de WhatsApp o Discord para enviarlo más tarde a una hora concreta. "
        "Calcula la fecha y hora exactas a partir de la hora actual que viene en cada mensaje del usuario."
    ),
    parameters={
        "platform": {"type": "string", "enum": ["whatsapp", "discord"]},
        "destination": {"type": "string", "description": "Contacto, amigo o canal (como en send_whatsapp / send_discord)."},
        "message": {"type": "string", "description": "Texto exacto del mensaje."},
        "send_at": {"type": "string", "description": "Fecha y hora local en formato 'AAAA-MM-DD HH:MM' (24 h)."},
    },
    confirm=_confirm_question,
)
def schedule_message(platform: str, destination: str, message: str, send_at: str) -> str:
    when = parse_time(send_at)
    if when <= datetime.now():
        return "Esa hora ya pasó; dígame otra."
    if platform == "whatsapp" and not messaging.find_contact(destination):
        return f"No tengo a {destination} en los contactos de WhatsApp."
    SCHEDULER.add(platform, destination, message, when)
    return f"Listo, lo enviaré {spoken_time(when)}. Recuerde dejarme encendido."


@registry.tool(
    name="list_scheduled_messages",
    description="Lista los mensajes programados pendientes (con su número, para poder cancelarlos).",
)
def list_scheduled_messages() -> str:
    items = SCHEDULER.pending()
    if not items:
        return "No hay mensajes programados."
    return "\n".join(
        f"#{i.id}: {spoken_time(i.when)} por {i.platform} a {i.destination}: {i.message}" for i in items
    )


@registry.tool(
    name="cancel_scheduled_message",
    quick=True,
    description="Cancela un mensaje programado por su número (usa antes list_scheduled_messages si no lo sabes).",
    parameters={"message_id": {"type": "integer"}},
)
def cancel_scheduled_message(message_id: int) -> str:
    item = SCHEDULER.cancel(message_id)
    if item is None:
        return f"No hay ningún mensaje programado pendiente con el número {message_id}."
    return f"Cancelado el mensaje para {item.destination}."
