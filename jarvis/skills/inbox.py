"""Mensajes recibidos: Jarvis te los anuncia y puedes preguntarle por ellos."""
from __future__ import annotations

from jarvis.config import load_settings
from jarvis.services.notifications import NotificationWatcher
from jarvis.skills.registry import registry

_settings = load_settings()
WATCHER = NotificationWatcher(_settings.notify_apps, read_text=_settings.notify_read_text)


@registry.tool(
    name="get_recent_messages",
    description="Devuelve los últimos mensajes recibidos (WhatsApp, Discord...) que Jarvis vio en las notificaciones.",
)
def get_recent_messages() -> str:
    if not WATCHER.recent:
        return "No he visto mensajes nuevos desde que me encendí."
    return "\n".join(f"{m.time:%H:%M} {m.app} — {m.sender}: {m.text}" for m in list(WATCHER.recent)[-10:])
