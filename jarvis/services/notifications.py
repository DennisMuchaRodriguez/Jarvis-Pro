"""Avisos de mensajes recibidos (WhatsApp, Discord, Telegram...).

Cómo se entera Jarvis: cuando te llega un mensaje, la app muestra una
notificación de Windows, y Windows la guarda en una pequeña base de datos:

    %LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db

Jarvis la lee (solo lectura) cada pocos segundos y anuncia las nuevas de las
apps que elijas (JARVIS_NOTIFY_APPS). No necesita contraseñas ni tocar
WhatsApp/Discord, pero sí que esas apps tengan las notificaciones de Windows
activadas. Discord no notifica mientras lo tienes en primer plano, y el modo
"No molestar" de Windows o de Discord también las silencia.
"""
from __future__ import annotations

import logging
import os
from contextlib import closing
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jarvis.core import events

log = logging.getLogger(__name__)

DEFAULT_DB = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Notifications" / "wpndatabase.db"

QUERY = """
    SELECT n.Id, h.PrimaryId, n.Payload
    FROM Notification n JOIN NotificationHandler h ON h.RecordId = n.HandlerId
    WHERE n.Id > ? AND n.Type = 'toast'
    ORDER BY n.Id
"""


@dataclass
class ReceivedMessage:
    time: datetime
    app: str
    sender: str
    text: str


def parse_toast(payload: bytes | str) -> tuple[str, str]:
    """Saca (título, cuerpo) del XML de una notificación. El título suele ser quien te escribe."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "ignore")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return "", ""
    texts = [t.text.strip() for t in root.iter("text") if t.text and t.text.strip()]
    if not texts:
        return "", ""
    return texts[0], " ".join(texts[1:])


class NotificationWatcher:
    def __init__(self, apps: list[str], read_text: bool = True, db_path: Path = DEFAULT_DB,
                 poll_every: float = 4.0) -> None:
        self.apps = [app.strip().lower() for app in apps if app.strip()]
        self.read_text = read_text
        self.db_path = db_path
        self.poll_every = poll_every
        self.recent: deque[ReceivedMessage] = deque(maxlen=30)
        self._last_id: int | None = None

    def _app_name(self, handler_id: str) -> str | None:
        handler = handler_id.lower()
        return next((app for app in self.apps if app in handler), None)

    def _query(self, last_id: int) -> list[tuple[int, str, bytes]]:
        with closing(sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2)) as db:
            return db.execute(QUERY, (last_id,)).fetchall()

    def poll(self) -> list[ReceivedMessage]:
        """Lee las notificaciones nuevas y anuncia las de las apps elegidas."""
        if self._last_id is None:  # al arrancar no anunciamos las viejas
            rows = self._query(0)
            self._last_id = rows[-1][0] if rows else 0
            return []

        new: list[ReceivedMessage] = []
        for row_id, handler, payload in self._query(self._last_id):
            self._last_id = row_id
            app = self._app_name(handler or "")
            if not app:
                continue
            sender, text = parse_toast(payload)
            if sender:
                new.append(ReceivedMessage(datetime.now(), app.capitalize(), sender, text))
        self.recent.extend(new)
        if new:
            events.post(events.Event(self._announcement(new)))
        return new

    def _announcement(self, messages: list[ReceivedMessage]) -> str:
        if len(messages) > 3:
            senders = ", ".join(dict.fromkeys(m.sender for m in messages))
            return f"Tiene {len(messages)} mensajes nuevos de {senders}."
        parts = []
        for m in messages:
            if self.read_text and m.text:
                parts.append(f"Mensaje de {m.sender} por {m.app}: {m.text}")
            else:
                parts.append(f"Tiene un mensaje de {m.sender} por {m.app}.")
        return " ".join(parts)

    def start(self) -> bool:
        if not self.db_path.exists():
            log.info("No encontré la base de notificaciones de Windows; avisos de mensajes desactivados.")
            return False

        def loop() -> None:
            failures = 0
            while failures < 20:
                try:
                    self.poll()
                    failures = 0
                except sqlite3.Error as exc:
                    failures += 1
                    log.debug("No pude leer las notificaciones (%s)", exc)
                time.sleep(self.poll_every)
            log.warning("Desactivo los avisos de mensajes: no puedo leer las notificaciones de Windows.")

        threading.Thread(target=loop, name="notificaciones", daemon=True).start()
        return True
