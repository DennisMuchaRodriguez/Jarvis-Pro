"""Habilidades de Jarvis.

Para añadir una habilidad nueva:
  1. Crea un archivo en esta carpeta (por ejemplo spotify.py).
  2. Escribe funciones decoradas con @registry.tool (mira system.py de ejemplo).
  3. Impórtalo abajo en load_skills().
"""
from jarvis.skills.registry import ToolRegistry, registry


def load_skills() -> ToolRegistry:
    # Importar cada módulo ejecuta sus decoradores y registra sus habilidades.
    from jarvis.skills import (  # noqa: F401
        apps, assistant, discord, inbox, messaging, projects, scheduling, system, web,
    )

    return registry
