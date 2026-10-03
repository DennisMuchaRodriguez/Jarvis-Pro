"""Grabador de frases: decide cuándo empiezas a hablar y cuándo terminaste.

Antes usábamos el detector de SpeechRecognition, que solo mira el VOLUMEN:
si hablas lejos del micrófono tu voz queda por debajo del umbral, y cualquier
pausa corta (respirar, pensar) se toma como el final de la orden.

Ahora el audio se analiza en trozos de 30 ms con un detector de voz (VAD,
el mismo que usa WebRTC en Google Meet/Discord). Reconoce la VOZ HUMANA por
su forma, no por el volumen, así que funciona aunque hables bajito o lejos.

    trozos:  . . . . v v . v v v v . . v v v . . . . . . . . . . .
                     └ empieza (4 de 10 con voz)        └ termina tras
             ◀── pre-roll ──▶                              1.2 s de silencio
             (guardamos 0.8 s antes para no perder la primera sílaba)

Como el detector también es sensible al volumen, primero ajustamos la
ganancia según el ruido de la habitación (ver VoiceDetector). Y antes de
transcribir, subimos el volumen de la grabación
(normalización) para que el reconocimiento entienda mejor las voces lejanas.

Prueba tu micrófono con:  python -m jarvis.audio.recorder
"""
from __future__ import annotations

import logging
import queue
import time
from collections import deque

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000   # 480 muestras
FRAME_BYTES = FRAME_SAMPLES * 2                  # int16 = 2 bytes por muestra

WAITING, RECORDING, DONE = "waiting", "recording", "done"


class PhraseSegmenter:
    """Lógica pura (sin micrófono): recibe trozos de 30 ms marcados como voz/no voz."""

    def __init__(
        self,
        silence_end: float = 1.2,     # segundos de silencio que marcan el final
        max_phrase: float = 20.0,     # corte de seguridad
        pre_roll: float = 0.8,        # audio que guardamos antes de detectar la voz
        start_window: int = 10,       # ventana para decidir que empezaste a hablar (300 ms)
        start_ratio: float = 0.4,     # ...con al menos 4 de cada 10 trozos con voz
        min_speech: float = 0.25,     # menos voz que esto = ruido (un golpe, una tos)
    ) -> None:
        self.silence_frames = max(1, int(silence_end * 1000 / FRAME_MS))
        self.max_frames = int(max_phrase * 1000 / FRAME_MS)
        self.min_speech_frames = int(min_speech * 1000 / FRAME_MS)
        self.start_ratio = start_ratio
        self._pre_roll: deque[tuple[bytes, bool]] = deque(maxlen=int(pre_roll * 1000 / FRAME_MS))
        self._start: deque[bool] = deque(maxlen=start_window)
        self._recent: deque[bool] = deque(maxlen=self.silence_frames)
        self._frames: list[bytes] = []
        self._speech_frames = 0
        self.state = WAITING

    def push(self, frame: bytes, is_speech: bool) -> str:
        if self.state == WAITING:
            self._pre_roll.append((frame, is_speech))
            self._start.append(is_speech)
            if len(self._start) == self._start.maxlen and sum(self._start) >= self.start_ratio * len(self._start):
                self.state = RECORDING
                self._frames = [f for f, _ in self._pre_roll]
                self._speech_frames = sum(s for _, s in self._pre_roll)
                self._recent.clear()
            return self.state

        if self.state == RECORDING:
            self._frames.append(frame)
            self._speech_frames += is_speech
            self._recent.append(is_speech)
            # Terminó si en el último `silence_end` casi no hubo voz (tolera ruiditos sueltos).
            finished = len(self._recent) == self._recent.maxlen and sum(self._recent) <= 0.1 * len(self._recent)
            if finished or len(self._frames) >= self.max_frames:
                if self._speech_frames < self.min_speech_frames:
                    self._reset_to_waiting()  # era ruido, seguimos esperando
                else:
                    self.state = DONE
        return self.state

    def _reset_to_waiting(self) -> None:
        self.state = WAITING
        self._frames = []
        self._speech_frames = 0
        self._pre_roll.clear()
        self._start.clear()

    def audio(self) -> bytes:
        return b"".join(self._frames)


def normalize(samples: np.ndarray, max_gain: float = 8.0) -> tuple[np.ndarray, float]:
    """Sube el volumen para que el pico quede cerca del máximo. Devuelve (audio, ganancia)."""
    peak = float(np.percentile(np.abs(samples.astype(np.float32)), 99.9))
    if peak < 1:
        return samples, 1.0
    gain = min(0.8 * 32767 / peak, max_gain)
    if gain <= 1.0:
        return samples, 1.0
    boosted = np.clip(samples.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
    return boosted, gain


class VoiceDetector:
    """¿Este trozo de 30 ms tiene voz? Se crea uno nuevo para cada frase.

    webrtcvad también depende del volumen: una voz lejana le parece "silencio".
    Por eso, justo después del bip, medimos 300 ms el ruido de la habitación y
    elegimos una ganancia que lleve ese ruido a un nivel fijo. En una habitación
    silenciosa la voz lejana se amplifica mucho; en una ruidosa casi nada, para
    no confundir ruido con voz. La ganancia NO cambia durante la frase: si
    cambiara, el detector confundiría el ruido amplificado con alguien hablando.

    Lo que digas durante esos primeros instantes no se pierde: queda en el
    pre-roll del PhraseSegmenter. Sin webrtcvad, se decide solo por volumen.
    """

    TARGET_NOISE = 0.008 * 32768   # nivel al que llevamos el ruido de fondo
    CALIBRATION_FRAMES = 10        # 300 ms midiendo el ruido
    WARMUP_FRAMES = 10             # 300 ms más mientras webrtcvad se adapta

    def __init__(self, aggressiveness: int = 1, max_gain: float = 8.0) -> None:
        try:
            import webrtcvad

            self._vad = webrtcvad.Vad(max(0, min(aggressiveness, 3)))
        except ImportError:
            log.warning("webrtcvad no está instalado; uso detección por volumen (peor). pip install webrtcvad-wheels")
            self._vad = None
        self.max_gain = max_gain
        self._levels: list[float] = []
        self._frames_seen = 0
        self.noise_floor: float | None = None
        self.gain = 1.0

    def __call__(self, frame: bytes) -> bool:
        samples = np.frombuffer(frame, np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self._frames_seen += 1

        if self._frames_seen <= self.CALIBRATION_FRAMES:
            self._levels.append(rms)
            return False
        if self.noise_floor is None:
            self.noise_floor = max(float(np.percentile(self._levels, 20)), 1.0)
            self.gain = min(max(self.TARGET_NOISE / self.noise_floor, 1.0), self.max_gain)
            log.debug("Ruido de fondo %.0f → ganancia del detector x%.1f", self.noise_floor, self.gain)

        if self._vad is None:
            return rms > self.noise_floor * 2.5
        if self.gain > 1.0:
            frame = np.clip(samples * self.gain, -32768, 32767).astype(np.int16).tobytes()
        speech = self._vad.is_speech(frame, SAMPLE_RATE)
        return speech and self._frames_seen > self.CALIBRATION_FRAMES + self.WARMUP_FRAMES


def parse_device(device: str) -> int | str | None:
    """'' = micrófono predeterminado; '3' = índice; 'Razer' = parte del nombre."""
    device = device.strip()
    if not device:
        return None
    return int(device) if device.isdigit() else device


def play_beep() -> None:
    """Bip corto para que sepas que ya puedes hablar."""
    import sounddevice as sd

    t = np.linspace(0, 0.12, int(SAMPLE_RATE * 0.12), endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 880 * t) * np.hanning(len(t))
    sd.play(tone.astype(np.float32), SAMPLE_RATE)
    sd.wait()


class PhraseRecorder:
    def __init__(
        self,
        device: str = "",
        vad_aggressiveness: int = 1,
        silence_end: float = 1.2,
        max_phrase: float = 20.0,
        max_gain: float = 8.0,
        beep: bool = True,
    ) -> None:
        self.device = parse_device(device)
        self.vad_aggressiveness = vad_aggressiveness
        self.silence_end = silence_end
        self.max_phrase = max_phrase
        self.max_gain = max_gain
        self.beep = beep

    def record(self, timeout: float) -> np.ndarray | None:
        """Graba una frase completa (int16, 16 kHz). None si no hablaste en `timeout` segundos."""
        import sounddevice as sd

        if self.beep:
            play_beep()  # antes de abrir el micrófono, para que el bip no se grabe
        frames: queue.Queue[bytes] = queue.Queue()
        segmenter = PhraseSegmenter(silence_end=self.silence_end, max_phrase=self.max_phrase)
        detector = VoiceDetector(self.vad_aggressiveness, self.max_gain)

        def on_audio(indata, frame_count, time_info, status) -> None:
            frames.put(bytes(indata))

        print("🎙️  Te escucho...", flush=True)
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, channels=1,
                               dtype="int16", device=self.device, callback=on_audio):
            deadline = time.monotonic() + timeout
            while True:
                try:
                    frame = frames.get(timeout=1)
                except queue.Empty:
                    continue
                if len(frame) != FRAME_BYTES:
                    continue
                previous = segmenter.state
                state = segmenter.push(frame, detector(frame))
                if state == RECORDING and previous == WAITING:
                    print("   ● grabando...", flush=True)
                if state == DONE:
                    break
                if state == WAITING and time.monotonic() > deadline:
                    return None

        samples = np.frombuffer(segmenter.audio(), np.int16)
        boosted, gain = normalize(samples, self.max_gain)
        log.debug("Frase de %.1f s, volumen subido x%.1f", len(samples) / SAMPLE_RATE, gain)
        return boosted


def _test_microphone() -> None:
    """Graba frases, muestra lo que entendió y guarda la última en prueba_microfono.wav para escucharla."""
    import wave

    from jarvis.audio.speech_to_text import SpeechToText
    from jarvis.config import load_settings

    stt = SpeechToText(load_settings())
    print("Di una frase larga, con pausas, desde donde normalmente le hablarás a Jarvis. Ctrl+C para salir.\n")
    try:
        while True:
            samples = stt.recorder.record(timeout=15)
            if samples is None:
                print("   (no detecté voz)\n")
                continue
            with wave.open("prueba_microfono.wav", "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(samples.tobytes())
            print(f"   ✓ grabé {len(samples) / SAMPLE_RATE:.1f} s → prueba_microfono.wav")
            print(f"   Entendí: {stt.transcribe(samples)!r}\n")
    except KeyboardInterrupt:
        print()

if __name__ == "__main__":
    _test_microphone()
