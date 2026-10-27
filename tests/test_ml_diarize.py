"""Test per src/ml/diarize.py — clustering speaker su embedding iniettati
(niente resemblyzer/modello: encoder finto deterministico)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.diarize import attach_speakers, diarize_segments

SR = 16000


class FakeEncoder:
    """Encoder finto: embedding prefissati per posizione del segmento."""

    def __init__(self, embeddings):
        self._embeddings = list(embeddings)
        self._i = 0

    def embed_utterance(self, clip):
        emb = self._embeddings[self._i]
        self._i += 1
        return emb


def _segments(n, dur=2.0):
    return [
        {"start": i * dur, "end": (i + 1) * dur, "text": f"seg {i}"} for i in range(n)
    ]


def _wav(seconds):
    rng = np.random.default_rng(7)
    return rng.standard_normal(int(seconds * SR)).astype(np.float32)


def test_cluster_two_speakers_aba():
    """Embedding [a, a, b, a] -> [S1, S1, S2, S1]: il ritorno al primo
    parlante (ABA) riassegnato al cluster originale."""
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    enc = FakeEncoder([a, a, b, a])
    labels = diarize_segments(_wav(8.0), SR, _segments(4), encoder=enc)
    assert labels == ["S1", "S1", "S2", "S1"]


def test_single_speaker_one_cluster():
    a = np.array([1.0, 0.0])
    near = np.array([0.99, 0.02])  # stessa direzione circa
    enc = FakeEncoder([a, near, a])
    labels = diarize_segments(_wav(6.0), SR, _segments(3), encoder=enc)
    assert labels == ["S1", "S1", "S1"]


def test_short_segment_inherits_previous_label():
    """Segmenti sotto MIN_SEG_SECONDS: niente embedding, eredita l'etichetta."""
    a = np.array([1.0, 0.0])
    enc = FakeEncoder([a, a])  # il segmento corto non consuma embedding
    segs = [
        {"start": 0.0, "end": 2.0, "text": "lungo"},
        {"start": 2.0, "end": 2.3, "text": "corto"},
        {"start": 2.3, "end": 4.3, "text": "lungo 2"},
    ]
    labels = diarize_segments(_wav(5.0), SR, segs, encoder=enc)
    assert labels == ["S1", "S1", "S1"]


def test_attach_speakers_contract():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "x"},
        {"start": 1.0, "end": 2.0, "text": "y"},
    ]
    attach_speakers(segs, ["S1", "S2"])
    assert segs[0]["speaker"] == "S1" and segs[1]["speaker"] == "S2"


def test_fake_engine_diarize_adds_speakers():
    from src.ml.asr import FakeAsrEngine

    out = FakeAsrEngine().transcribe(b"audio", "clip.ogg", diarize=True)
    speakers = [s["speaker"] for s in out["segments"]]
    assert speakers == ["S1", "S2"]
    out_plain = FakeAsrEngine().transcribe(b"audio", "clip.ogg")
    assert all("speaker" not in s for s in out_plain["segments"])
