"""Teclado y consola en lugar de micrófono y altavoces (python main.py --texto).

Sirve para probar el cerebro y las habilidades sin instalar nada de audio.
"""
from __future__ import annotations


class KeyboardInput:
    def listen(self) -> str | None:
        try:
            text = input("Tú: ").strip()
        except EOFError:
            raise KeyboardInterrupt from None
        return text or None


class ConsoleOutput:
    def say(self, text: str) -> None:
        print(f"Jarvis: {text}")
