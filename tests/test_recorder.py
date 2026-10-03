import numpy as np

from jarvis.audio.recorder import DONE, FRAME_BYTES, FRAME_MS, RECORDING, WAITING, PhraseSegmenter, normalize

FRAME = b"\x00" * FRAME_BYTES


def feed(segmenter: PhraseSegmenter, pattern: str) -> list[str]:
    """'v' = 30 ms con voz, '.' = 30 ms sin voz. Devuelve el estado tras cada trozo."""
    return [segmenter.push(FRAME, symbol == "v") for symbol in pattern]


def frames(seconds: float) -> int:
    return int(seconds * 1000 / FRAME_MS)


def test_short_pauses_do_not_cut_the_phrase():
    seg = PhraseSegmenter(silence_end=1.2)
    states = feed(seg, "." * 20 + "v" * 30 + "." * frames(0.8) + "v" * 30)  # pausa de 0.8 s a mitad de frase
    assert DONE not in states and states[-1] == RECORDING


def test_phrase_ends_after_silence():
    seg = PhraseSegmenter(silence_end=1.2)
    states = feed(seg, "v" * 30 + "." * (frames(1.2) + 1))
    assert states[-1] == DONE


def test_pre_roll_keeps_the_first_syllable():
    seg = PhraseSegmenter(silence_end=0.3, pre_roll=0.5)
    feed(seg, "." * 30 + "v" * 20 + "." * 20)
    recorded = len(seg.audio()) // FRAME_BYTES
    assert recorded >= 20 + frames(0.5) - 10  # incluye audio de antes de detectar la voz


def test_scattered_noise_does_not_start_recording():
    seg = PhraseSegmenter()
    states = feed(seg, "v...." * 40)  # 20% de trozos con "voz": ruido
    assert set(states) == {WAITING}


def test_isolated_noise_bursts_are_discarded():
    seg = PhraseSegmenter(silence_end=0.6, min_speech=0.5)
    states = feed(seg, "." * 10 + "vvvvvv" + "." * 40)  # 180 ms de golpe
    assert DONE not in states and states[-1] == WAITING


def test_max_phrase_cuts_endless_audio():
    seg = PhraseSegmenter(max_phrase=1.0)
    assert feed(seg, "v" * 60)[-1] == DONE


def test_normalize_boosts_quiet_voice_with_limit():
    quiet = (np.sin(np.linspace(0, 100, 16000)) * 1000).astype(np.int16)
    boosted, gain = normalize(quiet, max_gain=8)
    assert gain == 8 and np.abs(boosted).max() > 7000
    loud = (np.sin(np.linspace(0, 100, 16000)) * 30000).astype(np.int16)
    assert normalize(loud)[1] == 1.0


def test_detector_ignores_its_warmup_and_steady_noise():
    from jarvis.audio.recorder import FRAME_SAMPLES, VoiceDetector

    rng = np.random.default_rng(0)
    detector = VoiceDetector(aggressiveness=1, max_gain=8)
    noise = [(rng.normal(0, 30, FRAME_SAMPLES)).astype(np.int16).tobytes() for _ in range(100)]
    decisions = [detector(frame) for frame in noise]
    assert not any(decisions[:20])          # calibración + arranque de webrtcvad
    assert sum(decisions) <= 5              # ruido de fondo constante ≠ voz
    assert 1.0 < detector.gain <= 8         # cuarto silencioso → amplifica
