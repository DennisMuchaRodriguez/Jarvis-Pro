"""Detección de doble aplauso.

Cómo funciona
-------------
El micrófono entrega el audio en bloques pequeños (20 ms). Para cada bloque
medimos su pico de volumen y lo comparamos con el ruido de fondo de la
habitación. Un aplauso tiene una forma muy característica:

    volumen
      ▲      ┃                ┃
      │      ┃                ┃
      │      ┃▌               ┃▌
      │ ▁▁▁▁▁┃▌▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁┃▌▁▁▁▁   ← ruido de fondo
      └──────────────────────────────▶ tiempo
             ↑ < 0.15 s       ↑
             aplauso 1        aplauso 2  (separados 0.12 – 0.8 s)

- Es MUY fuerte comparado con el ruido de fondo.
- Es MUY corto (menos de ~150 ms). Una voz o una canción también pueden ser
  fuertes, pero duran mucho más, así que las descartamos.

Cuando vemos dos aplausos cortos separados por el intervalo correcto, damos
la señal de despertar.

La clase DoubleClapDetector no toca el micrófono: solo recibe bloques de
números. Así se puede probar con audio sintético (ver tests/). ClapListener
es quien abre el micrófono y le pasa los bloques.

Ejecuta `python -m jarvis.audio.clap_detector` para ver en vivo el volumen
de tu micrófono y calibrar JARVIS_CLAP_THRESHOLD.
"""
from __future__ import annotations

import logging
import math
import queue
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK_SECONDS = 0.02


class DoubleClapDetector:
    def __init__(
        self,
        threshold: float = 0.30,
        min_gap: float = 0.12,
        max_gap: float = 0.80,
        max_clap_duration: float = 0.15,
        noise_ratio: float = 6.0,
    ) -> None:
        self.threshold = threshold            # pico mínimo absoluto (0..1)
        self.min_gap = min_gap                # separación mínima entre aplausos
        self.max_gap = max_gap                # separación máxima entre aplausos
        self.max_clap_duration = max_clap_duration
        self.noise_ratio = noise_ratio        # cuántas veces más fuerte que el fondo
        self.noise_floor = 0.01               # se adapta solo al ruido de la habitación
        self._loud_since: float | None = None
        self._last_clap: float | None = None

    def reset(self) -> None:
        self._loud_since = None
        self._last_clap = None

    def process(self, block: np.ndarray, t: float) -> bool:
        """Procesa un bloque que empieza en el segundo `t`. Devuelve True al detectar doble aplauso."""
        peak = float(np.max(np.abs(block)))
        is_loud = peak >= self.threshold and peak >= self.noise_floor * self.noise_ratio

        if is_loud:
            if self._loud_since is None:
                self._loud_since = t
            return False

        if self._loud_since is None:
            # Bloque tranquilo: actualizamos lentamente el ruido de fondo.
            rms = math.sqrt(float(np.mean(np.square(block))))
            self.noise_floor = max(0.95 * self.noise_floor + 0.05 * rms, 1e-4)
            return False

        # Acaba de terminar un sonido fuerte: ¿fue corto como un aplauso?
        duration = t - self._loud_since
        self._loud_since = None
        if duration > self.max_clap_duration:
            self._last_clap = None  # era voz, música, un golpe largo...
            return False
        return self._register_clap(t)

    def _register_clap(self, t: float) -> bool:
        if self._last_clap is not None and self.min_gap <= t - self._last_clap <= self.max_gap:
            self.reset()
            return True
        self._last_clap = t
        return False


class ClapListener:
    """Abre el micrófono y bloquea hasta escuchar un doble aplauso."""

    def __init__(self, threshold: float, min_gap: float, max_gap: float, device: str = "") -> None:
        from jarvis.audio.recorder import parse_device

        self.device = parse_device(device)
        self.detector = DoubleClapDetector(threshold=threshold, min_gap=min_gap, max_gap=max_gap)

    def wait_for_double_clap(self, interrupt: Callable[[], bool] = lambda: False) -> bool:
        """Bloquea hasta oír un doble aplauso (True) o hasta que interrupt() sea True (False)."""
        import sounddevice as sd

        blocks: queue.Queue[np.ndarray] = queue.Queue()

        def on_audio(indata, frames, time_info, status) -> None:
            blocks.put(indata[:, 0].copy())

        self.detector.reset()
        t = 0.0
        # El micrófono se cierra al salir del "with", para que el reconocimiento de voz pueda usarlo.
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=int(SAMPLE_RATE * BLOCK_SECONDS),
            device=self.device,
            callback=on_audio,
        ):
            while True:
                block = blocks.get()
                if self.detector.process(block, t):
                    log.info("Doble aplauso detectado")
                    return True
                if interrupt():
                    return False
                t += len(block) / SAMPLE_RATE


def _calibrate() -> None:
    """Muestra el volumen del micrófono en vivo para elegir un buen umbral."""
    import sounddevice as sd

    from jarvis.audio.recorder import parse_device
    from jarvis.config import load_settings

    device = parse_device(load_settings().mic_device)
    print("Aplaude varias veces y habla normal. Fíjate en el pico de los aplausos (Ctrl+C para salir).")
    print("Pon JARVIS_CLAP_THRESHOLD un poco por debajo del pico de tus aplausos y por encima de tu voz.\n")

    def on_audio(indata, frames, time_info, status) -> None:
        peak = float(np.max(np.abs(indata)))
        bar = "█" * int(peak * 50)
        print(f"\rpico {peak:0.2f} |{bar:<50}|", end="", flush=True)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=int(SAMPLE_RATE * BLOCK_SECONDS), device=device, callback=on_audio):
        try:
            while True:
                sd.sleep(1000)
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    _calibrate()
