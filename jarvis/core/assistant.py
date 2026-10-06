"""El "director de orquesta": une oído, voz, aplausos, cerebro y servicios.

Estados de Jarvis:

    ┌──────────┐  doble aplauso   ┌───────────┐  frase  ┌──────────┐
    │ DORMIDO  │ ───────────────▶ │ ESCUCHANDO│ ──────▶ │ PENSANDO │
    └──────────┘                  └───────────┘         └──────────┘
          ▲                          ▲     │ silencio x N      │ habla / usa
          │   "descansa" o silencio  │     ▼                   ▼ herramientas
          └──────────────────────────┴──── vuelve a dormir ◀── responde

Mientras duerme, solo el detector de aplausos usa el micrófono (no se envía
nada a internet). Al despertar, el micrófono pasa al reconocimiento de voz.

Los servicios en segundo plano (mensajes programados, avisos de mensajes
recibidos) dejan eventos en un buzón (core/events.py). Este hilo los atiende
en los huecos: mientras duerme, o entre una orden y la siguiente.
"""
from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime

from jarvis.brain.llm import Brain
from jarvis.config import Settings
from jarvis.core import events
from jarvis.skills import load_skills
from jarvis.skills._helpers import IS_WINDOWS, normalize
from jarvis.skills.assistant import SLEEP_REQUESTED

log = logging.getLogger(__name__)

YES_WORDS = {"si", "claro", "dale", "hazlo", "adelante", "correcto", "confirmo", "afirmativo", "ok", "okay", "va", "envialo", "procede"}


def is_affirmative(answer: str | None) -> bool:
    """¿La respuesta hablada es un "sí"? Ante la duda, es un no."""
    words = re.findall(r"[a-z]+", normalize(answer or ""))
    if not words or words[0] == "no":
        return False
    return any(word in YES_WORDS for word in words) or "por supuesto" in " ".join(words)


def wait_for_enter_or_event() -> bool:
    """Espera a que pulses Enter (True) o a que llegue un evento (False)."""
    if IS_WINDOWS:
        import msvcrt

        while not events.pending():
            if msvcrt.kbhit() and msvcrt.getwch() in "\r\n":
                return True
            time.sleep(0.05)
        return False
    import select

    while not events.pending():
        if select.select([sys.stdin], [], [], 0.1)[0]:
            sys.stdin.readline()
            return True
    return False


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
        self.start_services()
        while True:
            woke_up = self.wait_for_wake_up()
            self.handle_events()
            if woke_up:
                self.conversation()

    def start_services(self) -> None:
        from jarvis.skills.inbox import WATCHER
        from jarvis.skills.scheduling import SCHEDULER

        SCHEDULER.start()
        if self.settings.notify_apps and WATCHER.start():
            log.info("Avisaré de mensajes de: %s", ", ".join(self.settings.notify_apps))

    def wait_for_wake_up(self) -> bool:
        """True si lo despertaste; False si lo interrumpió un evento (un aviso, un mensaje programado)."""
        self.mouth.wait()
        if self.text_mode:
            return True
        if self.claps:
            print("\n💤 Jarvis en reposo. Aplaude dos veces para despertarlo.", flush=True)
            return self.claps.wait_for_double_clap(interrupt=events.pending)
        print("\n💤 Jarvis en reposo. Pulsa Enter para despertarlo.", flush=True)
        return wait_for_enter_or_event()

    def conversation(self) -> None:
        self.brain.reset()
        self.brain.prewarm()  # mientras saluda y te escucha, se prepara el caché
        SLEEP_REQUESTED.clear()
        self.say(self.greeting())

        silent_rounds = 0
        while True:
            self.handle_events()
            text = self.listen()
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

    # ---- eventos de los servicios ------------------------------------------
    def handle_events(self) -> None:
        for event in events.drain():
            self.say(event.say)
            if event.action:
                self.mouth.wait()
                time.sleep(1.5)  # un respiro para que sueltes el teclado
                self.say(event.action())

    # ---- utilidades --------------------------------------------------------
    def say(self, text: str) -> None:
        self.mouth.say(text)

    def listen(self) -> str | None:
        self.mouth.wait()  # que Jarvis no se grabe a sí mismo
        return self.ears.listen()

    def confirm(self, question: str) -> bool:
        """Pregunta en voz alta y espera un sí/no. Lo usan las habilidades delicadas."""
        self.say(question)
        answer = self.listen()
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
