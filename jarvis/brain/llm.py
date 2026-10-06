"""Conversación con Claude usando herramientas (tool use).

El ciclo es así:

  1. Enviamos a Claude: la personalidad (system prompt), la lista de
     herramientas y el historial de la conversación con tu nueva orden.
  2. Claude responde con texto y/o con peticiones de herramientas
     ("tool_use"), por ejemplo: play_youtube(query="lofi para programar").
  3. Ejecutamos esas herramientas en tu PC y le devolvemos los resultados.
  4. Repetimos hasta que Claude termina (stop_reason == "end_turn").

Trucos de velocidad:
  - Streaming: cada frase se manda a la voz en cuanto Claude la escribe,
    sin esperar a que termine la respuesta completa.
  - Acciones rápidas (quick): si todas las herramientas pedidas son acciones
    que salieron bien ("Abriendo Spotify."), Jarvis dice el resultado y NO
    hace la segunda petición a Claude. Los resultados se le entregan junto
    con tu siguiente orden. Esto ahorra un viaje completo a la API.
  - Caché precalentado: al despertar, en segundo plano, se prepara el caché
    del prompt para que la primera orden responda más rápido.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

import anthropic

from jarvis.brain.prompts import build_system_prompt
from jarvis.config import Settings
from jarvis.skills.registry import ConfirmFn, ToolRegistry
from jarvis.skills.system import get_datetime

log = logging.getLogger(__name__)

MAX_STEPS = 10          # máximo de rondas de herramientas por orden
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Modelos que aceptan `fallbacks: "default"`: si un filtro de seguridad rechaza
# la petición por error, otro modelo la reintenta en el servidor.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def model_options(model: str, effort: str) -> tuple[dict[str, Any], str]:
    """Parámetros según el modelo. Devuelve (opciones de la petición, versión de búsqueda web)."""
    name = model.lower()
    if name.startswith("claude-haiku-4"):
        # Haiku 4.5: sin razonamiento extendido ni `effort`, y con la búsqueda web básica.
        return {}, "web_search_20250305"
    options: dict[str, Any] = {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}
    if name in FALLBACK_MODELS:
        options.update(betas=[FALLBACK_BETA], fallbacks="default")
    return options, "web_search_20260209"


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """'Hola. Ya voy, se' → (['Hola.'], 'Ya voy, se')"""
    parts = _SENTENCE_END.split(buffer)
    return [p for p in parts[:-1] if p.strip()], parts[-1]


class Brain:
    def __init__(self, settings: Settings, registry: ToolRegistry, client: anthropic.Anthropic | None = None) -> None:
        self.settings = settings
        self.registry = registry
        self.client = client or anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno
        self.options, web_search_type = model_options(settings.model, settings.effort)
        # Marca de caché explícita al final de la parte fija (herramientas + personalidad).
        self.system = [{"type": "text", "text": build_system_prompt(settings),
                        "cache_control": {"type": "ephemeral"}}]
        self.tools: list[dict[str, Any]] = registry.definitions()
        if settings.web_search:
            # Herramienta del servidor: la ejecuta Anthropic, no nuestro código.
            self.tools.append({"type": web_search_type, "name": "web_search", "max_uses": 3})
        self.messages: list[dict[str, Any]] = []
        self._pending_results: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Olvida la conversación (se llama cada vez que Jarvis se despierta)."""
        self.messages = []
        self._pending_results = []

    def prewarm(self) -> None:
        """Prepara el caché del prompt en segundo plano (max_tokens=0: no genera respuesta)."""
        def warm() -> None:
            try:
                self.client.beta.messages.create(
                    model=self.settings.model, max_tokens=0, system=self.system, tools=self.tools,
                    messages=[{"role": "user", "content": "warmup"}], **self.options,
                )
            except Exception as exc:
                log.debug("No se pudo precalentar el caché: %s", exc)

        threading.Thread(target=warm, name="precalentar", daemon=True).start()

    def think(self, user_text: str, speak: Callable[[str], None], confirm: ConfirmFn) -> None:
        """Procesa una orden. Habla con `speak` y pide confirmaciones con `confirm`."""
        # Resultados de acciones rápidas del turno anterior + la hora actual + tu orden.
        content = self._pending_results + [
            {"type": "text", "text": f"[Ahora: {get_datetime()}]"},
            {"type": "text", "text": user_text},
        ]
        self._pending_results = []
        self.messages.append({"role": "user", "content": content})
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
            response = self._stream_claude(speak)

            if response.stop_reason == "refusal":
                # Empezamos una conversación limpia para no arrastrar el tema rechazado.
                self.reset()
                speak("Me temo que no puedo ayudarle con eso.")
                return

            # Guardamos la respuesta COMPLETA (no solo el texto): Claude la necesita en la siguiente ronda.
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":
                continue  # la búsqueda web necesita otra ronda; reenviamos tal cual
            if response.stop_reason != "tool_use":
                return

            results, outcomes = [], []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                outcome = self.registry.execute(block.name, block.input, confirm)
                outcomes.append(outcome)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": outcome.text,
                    "is_error": outcome.is_error,
                })

            if all(o.quick and not o.is_error for o in outcomes):
                # Acción rápida: decimos el resultado y nos ahorramos la segunda petición.
                for outcome in outcomes:
                    if not outcome.declined:
                        speak(outcome.text)
                self._pending_results = results  # se entregan junto con tu próxima orden
                return
            # Todos los resultados van juntos en un solo mensaje.
            self.messages.append({"role": "user", "content": results})

        speak("Esto está llevando demasiados pasos; lo dejo aquí por ahora.")

    def _stream_claude(self, speak: Callable[[str], None]):
        """Pide la respuesta en streaming y habla cada frase en cuanto está completa."""
        buffer = ""
        with self.client.beta.messages.stream(
            model=self.settings.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            cache_control={"type": "ephemeral"},  # caché automático para el historial
            **self.options,
        ) as stream:
            for event in stream:
                if event.type == "text":
                    sentences, buffer = split_sentences(buffer + event.text)
                    for sentence in sentences:
                        speak(sentence)
                elif event.type == "content_block_stop" and buffer.strip():
                    speak(buffer)
                    buffer = ""
            response = stream.get_final_message()
        if buffer.strip():
            speak(buffer)
        return response
