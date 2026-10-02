import numpy as np

from jarvis.audio.clap_detector import BLOCK_SECONDS, SAMPLE_RATE, DoubleClapDetector

BLOCK = int(SAMPLE_RATE * BLOCK_SECONDS)
rng = np.random.default_rng(0)


def quiet() -> np.ndarray:
    return rng.normal(0, 0.005, BLOCK).astype(np.float32)


def loud() -> np.ndarray:
    return rng.normal(0, 0.3, BLOCK).clip(-1, 1).astype(np.float32)


def run(pattern: str) -> bool:
    """'.' = 20 ms de silencio, 'X' = 20 ms de sonido fuerte."""
    detector = DoubleClapDetector(threshold=0.3)
    t = 0.0
    for symbol in "." * 50 + pattern + "." * 10:  # 1 s de fondo para estimar el ruido
        if detector.process(loud() if symbol == "X" else quiet(), t):
            return True
        t += BLOCK_SECONDS
    return False


def test_double_clap_wakes_up():
    assert run("XX" + "." * 15 + "XX")      # dos aplausos separados ~0.35 s


def test_single_clap_does_not_wake_up():
    assert not run("XX" + "." * 60)


def test_claps_too_far_apart_do_not_wake_up():
    assert not run("XX" + "." * 60 + "XX")  # ~1.2 s entre aplausos


def test_long_sounds_are_not_claps():
    assert not run("X" * 30 + "." * 10 + "X" * 30)  # voz/música: sonidos largos


def test_quiet_sounds_are_ignored():
    detector = DoubleClapDetector(threshold=0.3)
    soft = np.full(BLOCK, 0.1, dtype=np.float32)
    t = 0.0
    for block in [quiet()] * 50 + [soft, quiet(), quiet(), quiet(), quiet(), soft, quiet()]:
        assert not detector.process(block, t)
        t += BLOCK_SECONDS
