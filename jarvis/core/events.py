"""Buzón de eventos de los servicios en segundo plano.

Los servicios (mensajes programados, avisos de mensajes recibidos) corren en
sus propios hilos, pero NUNCA hablan ni tocan el teclado directamente: dejan
un Event en este buzón y el hilo principal de Jarvis lo atiende cuando el
micrófono y los altavoces están libres. Así Jarvis no habla encima de sí mismo
ni graba su propia voz como si fuera una orden tuya.
"""
from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Callable


@dataclass
class Event:
    say: str                                      # lo que Jarvis anuncia
    action: Callable[[], str] | None = None       # (opcional) qué hacer después; devuelve un texto a decir


_EVENTS: queue.Queue[Event] = queue.Queue()


def post(event: Event) -> None:
    _EVENTS.put(event)


def pending() -> bool:
    return not _EVENTS.empty()


def drain() -> list[Event]:
    events = []
    while True:
        try:
            events.append(_EVENTS.get_nowait())
        except queue.Empty:
            return events
