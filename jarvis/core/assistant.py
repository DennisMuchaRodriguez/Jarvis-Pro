"""El "director de orquesta": une oído, voz, aplausos y cerebro.

Estados de Jarvis:

    ┌──────────┐  doble aplauso   ┌───────────┐  frase  ┌──────────┐
    │ DORMIDO  │ ───────────────▶ │ ESCUCHANDO│ ──────▶ │ PENSANDO │
    └──────────┘                  └───────────┘         └──────────┘
          ▲                          ▲     │ silencio x N      │ habla / usa
          │   "descansa" o silencio  │     ▼                   ▼ herramientas
          └──────────────────────────┴──── vuelve a dormir ◀── responde

Mientras duerme, solo el detector de aplausos usa el micrófono (no se envía
nada a internet). Al despertar, el micrófono pasa al reconocimiento de voz.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from jarvis.brain.llm import Brain
from jarvis.config import Settings
from jarvis.skills import load_skills
from jarvis.skills._helpers import normalize
from jarvis.skills.assistant import SLEEP_REQUESTED

log = logging.getLogger(__name__)

YES_WORDS = {"si", "claro", "dale", "hazlo", "adelante", "correcto", "confirmo", "afirmativo", "ok", "okay", "va", "envialo", "procede"}


def is_affirmative(answer: str | None) -> bool:
    """¿La respuesta hablada es un "sí"? Ante la duda, es un no."""
    words = re.findall(r"[a-z]+", normalize(answer or ""))
    if not words or words[0] == "no":
        return False
    return any(word in YES_WORDS for word in words) or "por supuesto" in " ".join(words)


class Jarvis:
    def __init__(self, settings: Settings, text_mode: bool = False, use_claps: bool = True) -> None:
        self.settings = settings
        self.text_mode = text_mode
        self.brain = Brain(settings, load_skills())

        if text_mode:
            from jarvis.audio.console import ConsoleOutput, KeyboardInput

            self.ears, self.mouth = KeyboardInput(), ConsoleOutput()
        else:
            from jarvis.audio.speech_to_text import SpeechToText
            from jarvis.audio.text_to_speech import TextToSpeech

            self.ears, self.mouth = SpeechToText(settings), TextToSpeech(settings)

        self.claps = None
        if use_claps and not text_mode:
            from jarvis.audio.clap_detector import ClapListener

            self.claps = ClapListener(
                settings.clap_threshold, settings.clap_min_gap, settings.clap_max_gap, settings.mic_device
            )

    # ---- ciclo principal -------------------------------------------------
    def run(self) -> None:
        while True:
            self.wait_for_wake_up()
            self.conversation()

    def wait_for_wake_up(self) -> None:
        if self.claps:
            print("\n💤 Jarvis en reposo. Aplaude dos veces para despertarlo.")
            self.claps.wait_for_double_clap()
        elif not self.text_mode:
            input("\n💤 Jarvis en reposo. Pulsa Enter para despertarlo.")

    def conversation(self) -> None:
        self.brain.reset()
        SLEEP_REQUESTED.clear()
        self.say(self.greeting())

        silent_rounds = 0
        while True:
            text = self.ears.listen()
            if not text:
                silent_rounds += 1
                if silent_rounds >= self.settings.idle_rounds and not self.text_mode:
                    self.say(f"Estaré aquí si me necesita, {self.settings.user_title}.")
                    return
                continue
            silent_rounds = 0
            if not self.text_mode:
                print(f"Tú: {text}")

            self.brain.think(text, speak=self.say, confirm=self.confirm)
            if SLEEP_REQUESTED.is_set():
                return

    # ---- utilidades --------------------------------------------------------
    def say(self, text: str) -> None:
        self.mouth.say(text)

    def confirm(self, question: str) -> bool:
        """Pregunta en voz alta y espera un sí/no. Lo usan las habilidades delicadas."""
        self.say(question)
        answer = self.ears.listen()
        if not self.text_mode:
            print(f"Tú: {answer or '(silencio)'}")
        approved = is_affirmative(answer)
        if not approved:
            self.say("Entendido, lo cancelo.")
        return approved

    def greeting(self) -> str:
        hour = datetime.now().hour
        saludo = "Buenos días" if 5 <= hour < 12 else "Buenas tardes" if 12 <= hour < 20 else "Buenas noches"
        return f"{saludo}, {self.settings.user_title}. ¿En qué puedo ayudarle?"
