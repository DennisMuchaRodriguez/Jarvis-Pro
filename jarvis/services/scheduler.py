"""Mensajes programados: "a las 9 mándale a mamá que ya voy".

Se guardan en jarvis_datos/programados.json (no se sube a GitHub), así que
sobreviven si cierras Jarvis. Un hilo revisa cada 10 segundos si alguno ya
toca; cuando toca, deja un Event para que el hilo principal avise y lo envíe.

Jarvis tiene que estar encendido a esa hora. Si estaba apagado y el mensaje
se retrasó menos de 2 horas, lo envía al encenderse; si fue más, te avisa.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from jarvis.core import events

log = logging.getLogger(__name__)

MAX_DELAY = timedelta(hours=2)
CHECK_EVERY = 10  # segundos

Sender = Callable[[str, str], str]  # (destino, mensaje) -> texto del resultado


@dataclass
class ScheduledMessage:
    id: int
    platform: str
    destination: str
    message: str
    send_at: str              # "2026-10-06T21:30"
    status: str = "pendiente"  # pendiente | enviando | enviado | fallido | perdido

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.send_at)


def spoken_time(when: datetime, now: datetime | None = None) -> str:
    """'hoy a las 21:30', 'mañana a las 08:00', 'el 12/10 a las 19:00'."""
    now = now or datetime.now()
    days = (when.date() - now.date()).days
    day = "hoy" if days == 0 else "mañana" if days == 1 else f"el {when:%d/%m}"
    return f"{day} a las {when:%H:%M}"


class Scheduler:
    def __init__(self, path: Path, senders: dict[str, Sender] | None = None) -> None:
        self.path = path
        self.senders = senders or {}
        self._lock = threading.Lock()
        self._items = self._load()

    # ---- almacenamiento ---------------------------------------------------
    def _load(self) -> list[ScheduledMessage]:
        if not self.path.exists():
            return []
        try:
            return [ScheduledMessage(**raw) for raw in json.loads(self.path.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, TypeError) as exc:
            log.error("No pude leer %s: %s", self.path, exc)
            return []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(item) for item in self._items]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- lo que usan las habilidades -------------------------------------
    def add(self, platform: str, destination: str, message: str, when: datetime) -> ScheduledMessage:
        with self._lock:
            next_id = max((item.id for item in self._items), default=0) + 1
            item = ScheduledMessage(next_id, platform, destination, message, when.isoformat(timespec="minutes"))
            self._items.append(item)
            self._save()
            return item

    def pending(self) -> list[ScheduledMessage]:
        with self._lock:
            return sorted((i for i in self._items if i.status == "pendiente"), key=lambda i: i.when)

    def cancel(self, item_id: int) -> ScheduledMessage | None:
        with self._lock:
            for item in self._items:
                if item.id == item_id and item.status == "pendiente":
                    self._items.remove(item)
                    self._save()
                    return item
            return None

    # ---- el reloj ---------------------------------------------------------
    def check_due(self, now: datetime | None = None) -> None:
        """Pasa a eventos los mensajes que ya tocan. Lo llama el hilo cada 10 s."""
        now = now or datetime.now()
        with self._lock:
            due = [i for i in self._items if i.status == "pendiente" and i.when <= now]
            for item in due:
                if now - item.when > MAX_DELAY:
                    item.status = "perdido"
                    events.post(events.Event(
                        f"No pude enviar el mensaje programado para {item.destination} de las "
                        f"{item.when:%H:%M} porque yo estaba apagado."))
                else:
                    item.status = "enviando"
                    events.post(events.Event(
                        f"Enviando el mensaje programado a {item.destination} por {item.platform}. "
                        "No toque el teclado unos segundos.",
                        action=lambda item=item: self._send(item)))
            if due:
                self._save()

    def _send(self, item: ScheduledMessage) -> str:
        sender = self.senders.get(item.platform)
        try:
            if sender is None:
                raise ValueError(f"plataforma desconocida: {item.platform}")
            result = sender(item.destination, item.message)
            status = "enviado"
        except Exception as exc:
            log.exception("Falló el mensaje programado %s", item.id)
            result = f"No pude enviar el mensaje programado a {item.destination}: {exc}"
            status = "fallido"
        with self._lock:
            item.status = status
            # Guardamos solo el historial reciente para que el archivo no crezca sin fin.
            done = [i for i in self._items if i.status not in ("pendiente", "enviando")]
            for old in done[:-50]:
                self._items.remove(old)
            self._save()
        return result

    def start(self) -> None:
        with self._lock:  # un envío que quedó a medias al cerrar Jarvis se reintenta
            for item in self._items:
                if item.status == "enviando":
                    item.status = "pendiente"

        def loop() -> None:
            while True:
                try:
                    self.check_due()
                except Exception:
                    log.exception("Error revisando mensajes programados")
                time.sleep(CHECK_EVERY)

        threading.Thread(target=loop, name="programados", daemon=True).start()
