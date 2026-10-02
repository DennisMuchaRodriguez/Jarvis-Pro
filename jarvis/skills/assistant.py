"""Habilidades sobre el propio Jarvis."""
from __future__ import annotations

import threading

from jarvis.skills.registry import registry

# La conversación (core/assistant.py) revisa esta bandera después de cada respuesta.
SLEEP_REQUESTED = threading.Event()


@registry.tool(
    name="go_to_sleep",
    description=(
        "Termina la conversación y vuelve al modo reposo (esperando aplausos). Úsala cuando "
        "el usuario se despida, dé las gracias como cierre o pida que descanses."
    ),
)
def go_to_sleep() -> str:
    SLEEP_REQUESTED.set()
    return "Entrando en reposo tras esta respuesta. Despídete en pocas palabras."
