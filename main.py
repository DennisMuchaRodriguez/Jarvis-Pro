"""Punto de entrada de Jarvis.

    python main.py                 # modo completo: aplausos + voz
    python main.py --sin-aplausos  # despierta con Enter en lugar de aplausos
    python main.py --texto         # escribe en la consola en vez de hablar (ideal para probar)
    python main.py --debug         # muestra todo lo que ocurre por dentro
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from jarvis.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. — asistente por voz")
    parser.add_argument("--texto", action="store_true", help="usar teclado y consola en lugar de micrófono y voz")
    parser.add_argument("--sin-aplausos", action="store_true", help="despertar con Enter en lugar de aplausos")
    parser.add_argument("--debug", action="store_true", help="mostrar logs detallados")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Las librerías de red son muy ruidosas en INFO.
    for noisy in ("httpx", "httpx2", "anthropic", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        sys.exit("Falta ANTHROPIC_API_KEY. Copia .env.example como .env y pon tu clave.")

    from jarvis.core.assistant import Jarvis

    jarvis = Jarvis(load_settings(), text_mode=args.texto, use_claps=not args.sin_aplausos)
    try:
        jarvis.run()
    except KeyboardInterrupt:
        print("\nHasta luego.")


if __name__ == "__main__":
    main()
