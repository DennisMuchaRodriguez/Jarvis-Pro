"""Registro de habilidades (las "herramientas" que Claude puede usar).

Cada habilidad es una función normal de Python decorada con @registry.tool.
El decorador guarda:
  - name / description: Claude los lee para decidir CUÁNDO usarla.
  - parameters: qué datos necesita (formato JSON Schema).
  - confirm: (opcional) pregunta que Jarvis te hará en voz alta antes de
    ejecutarla, para acciones delicadas como enviar mensajes o apagar el PC.
    Puede ser un texto con {campos} o una función que recibe los argumentos.
  - quick: True si es una ACCIÓN cuyo resultado se puede decir tal cual
    ("Abriendo Spotify."). Así Jarvis no vuelve a preguntarle a Claude qué
    decir después, y responde mucho más rápido. Las consultas (hora, batería...)
    no son quick: Claude necesita leer el resultado para contestarte.

Ejemplo:

    @registry.tool(
        name="open_calculator",
        description="Abre la calculadora.",
        quick=True,
    )
    def open_calculator() -> str:
        subprocess.Popen("calc")
        return "Calculadora abierta."

Lo que devuelve la función (un texto) se le envía a Claude como resultado.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

# La API acepta como máximo 20 herramientas en modo estricto ("strict") por petición.
MAX_STRICT_TOOLS = 20

ConfirmFn = Callable[[str], bool]


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    parameters: dict[str, dict] = field(default_factory=dict)
    confirm: str | Callable[..., str] | None = None
    quick: bool = False

    def definition(self, strict: bool) -> dict[str, Any]:
        definition: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters),
                "additionalProperties": False,
            },
        }
        if strict:
            definition["strict"] = True  # Claude siempre enviará argumentos que cumplan el esquema
        return definition

    def confirmation_question(self, args: dict[str, Any]) -> str | None:
        if self.confirm is None:
            return None
        return self.confirm(**args) if callable(self.confirm) else self.confirm.format(**args)


@dataclass
class ToolOutcome:
    text: str               # resultado para Claude (y para decirlo en voz alta si es quick)
    is_error: bool = False
    declined: bool = False  # el usuario dijo "no" a la confirmación
    quick: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, dict] | None = None,
        confirm: str | Callable[..., str] | None = None,
        quick: bool = False,
    ) -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(func: Callable[..., str]) -> Callable[..., str]:
            if name in self._tools:
                raise ValueError(f"Habilidad duplicada: {name}")
            self._tools[name] = Tool(name, description, func, parameters or {}, confirm, quick)
            return func

        return decorator

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        """Definiciones para Claude, en orden estable (así el prompt cacheado no cambia)."""
        return [self._tools[name].definition(name in self._strict_names()) for name in sorted(self._tools)]

    def _strict_names(self) -> set[str]:
        """Qué herramientas van en modo estricto (máximo MAX_STRICT_TOOLS).

        Solo lo necesitan las que tienen parámetros (sin parámetros no hay nada que
        validar), y primero las delicadas, las que piden confirmación. Si alguna se
        queda fuera, sigue funcionando: si Claude enviara datos mal formados, la
        función falla y Claude recibe el error para corregirse.
        """
        candidates = sorted(
            (tool for tool in self._tools.values() if tool.parameters),
            key=lambda tool: (tool.confirm is None, tool.name),
        )
        if len(candidates) > MAX_STRICT_TOOLS:
            log.warning("Hay %d habilidades con parámetros; solo %d pueden ser estrictas.",
                        len(candidates), MAX_STRICT_TOOLS)
        return {tool.name for tool in candidates[:MAX_STRICT_TOOLS]}

    def execute(self, name: str, args: dict[str, Any], confirm: ConfirmFn) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutcome(f"La habilidad '{name}' no existe.", is_error=True)
        question = tool.confirmation_question(args)
        if question and not confirm(question):
            return ToolOutcome("El usuario NO confirmó la acción; no se realizó.", declined=True, quick=True)
        log.info("Ejecutando %s(%s)", name, args)
        try:
            return ToolOutcome(str(tool.func(**args)), quick=tool.quick)
        except Exception as exc:
            log.exception("Falló la habilidad %s", name)
            return ToolOutcome(f"Error al ejecutar {name}: {exc}", is_error=True)


registry = ToolRegistry()
