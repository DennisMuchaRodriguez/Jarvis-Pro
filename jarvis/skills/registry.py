"""Registro de habilidades (las "herramientas" que Claude puede usar).

Cada habilidad es una función normal de Python decorada con @registry.tool.
El decorador guarda:
  - name / description: Claude los lee para decidir CUÁNDO usarla.
  - parameters: qué datos necesita (formato JSON Schema).
  - confirm: (opcional) pregunta que Jarvis te hará en voz alta antes de
    ejecutarla, para acciones delicadas como enviar mensajes o apagar el PC.

Ejemplo:

    @registry.tool(
        name="open_calculator",
        description="Abre la calculadora.",
    )
    def open_calculator() -> str:
        subprocess.Popen("calc")
        return "Calculadora abierta."

Lo que devuelve la función (un texto) se le envía a Claude como resultado,
y Claude lo usa para contestarte.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

ConfirmFn = Callable[[str], bool]


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    parameters: dict[str, dict] = field(default_factory=dict)
    confirm: str | None = None

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters),
                "additionalProperties": False,
            },
            "strict": True,  # Claude siempre enviará argumentos que cumplan el esquema
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, dict] | None = None,
        confirm: str | None = None,
    ) -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(func: Callable[..., str]) -> Callable[..., str]:
            if name in self._tools:
                raise ValueError(f"Habilidad duplicada: {name}")
            self._tools[name] = Tool(name, description, func, parameters or {}, confirm)
            return func

        return decorator

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        # Orden estable: así el prompt cacheado no cambia entre peticiones.
        return [self._tools[name].definition() for name in sorted(self._tools)]

    def execute(self, name: str, args: dict[str, Any], confirm: ConfirmFn) -> tuple[str, bool]:
        """Ejecuta una habilidad. Devuelve (resultado, es_error)."""
        tool = self._tools.get(name)
        if tool is None:
            return f"La habilidad '{name}' no existe.", True
        if tool.confirm and not confirm(tool.confirm.format(**args)):
            return "El usuario NO confirmó la acción; no se realizó.", False
        log.info("Ejecutando %s(%s)", name, args)
        try:
            return str(tool.func(**args)), False
        except Exception as exc:
            log.exception("Falló la habilidad %s", name)
            return f"Error al ejecutar {name}: {exc}", True


registry = ToolRegistry()
