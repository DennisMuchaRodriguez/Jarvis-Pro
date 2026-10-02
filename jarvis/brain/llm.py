"""Conversación con Claude usando herramientas (tool use).

El ciclo es así:

  1. Enviamos a Claude: la personalidad (system prompt), la lista de
     herramientas y el historial de la conversación con tu nueva orden.
  2. Claude responde con texto y/o con peticiones de herramientas
     ("tool_use"), por ejemplo: play_youtube(query="lofi para programar").
  3. Ejecutamos esas herramientas en tu PC y le devolvemos los resultados.
  4. Repetimos hasta que Claude termina (stop_reason == "end_turn").

Cada texto que Claude escribe se habla en voz alta en cuanto llega, así
Jarvis puede decir "Enseguida, señor" mientras abre algo.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import anthropic

from jarvis.brain.prompts import build_system_prompt
from jarvis.config import Settings
from jarvis.skills.registry import ConfirmFn, ToolRegistry

log = logging.getLogger(__name__)

MAX_STEPS = 10          # máximo de rondas de herramientas por orden
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class Brain:
    def __init__(self, settings: Settings, registry: ToolRegistry, client: anthropic.Anthropic | None = None) -> None:
        self.settings = settings
        self.registry = registry
        self.client = client or anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno
        self.system_prompt = build_system_prompt(settings)
        self.tools: list[dict[str, Any]] = registry.definitions()
        if settings.web_search:
            # Herramienta del servidor: la ejecuta Anthropic, no nuestro código.
            self.tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 3})
        self.messages: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Olvida la conversación (se llama cada vez que Jarvis se despierta)."""
        self.messages = []

    def think(self, user_text: str, speak: Callable[[str], None], confirm: ConfirmFn) -> None:
        """Procesa una orden. Habla con `speak` y pide confirmaciones con `confirm`."""
        self.messages.append({"role": "user", "content": user_text})
        try:
            self._run_loop(speak, confirm)
        except anthropic.AuthenticationError:
            self.reset()
            speak("Mi clave de acceso a la API no es válida. Revise ANTHROPIC_API_KEY en el archivo .env.")
        except anthropic.RateLimitError:
            self.reset()
            speak("Estoy recibiendo demasiadas peticiones. Deme unos segundos.")
        except anthropic.APIStatusError as exc:
            log.error("Error de la API (%s): %s", exc.status_code, exc.message)
            self.reset()
            speak("Tuve un problema al procesar eso. Inténtelo de nuevo.")
        except anthropic.APIConnectionError:
            self.reset()
            speak("No tengo conexión a internet en este momento.")

    def _run_loop(self, speak: Callable[[str], None], confirm: ConfirmFn) -> None:
        for _ in range(MAX_STEPS):
            response = self._call_claude()

            if response.stop_reason == "refusal":
                # Empezamos una conversación limpia para no arrastrar el tema rechazado.
                self.reset()
                speak("Me temo que no puedo ayudarle con eso.")
                return

            # Guardamos la respuesta COMPLETA (no solo el texto): Claude la necesita en la siguiente ronda.
            self.messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    speak(block.text)

            if response.stop_reason == "pause_turn":
                continue  # la búsqueda web necesita otra ronda; reenviamos tal cual
            if response.stop_reason != "tool_use":
                return

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output, is_error = self.registry.execute(block.name, block.input, confirm)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                })
            # Todos los resultados van juntos en un solo mensaje.
            self.messages.append({"role": "user", "content": results})

        speak("Esto está llevando demasiados pasos; lo dejo aquí por ahora.")

    def _call_claude(self):
        return self.client.beta.messages.create(
            model=self.settings.model,
            max_tokens=16000,
            system=self.system_prompt,
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.settings.effort},
            cache_control={"type": "ephemeral"},  # abarata las peticiones repetidas
            # Si un filtro de seguridad rechaza la petición por error, otro modelo la reintenta.
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
