"""Test per src/ml/asr.py — engine ASR astratto, fake e factory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.asr import AsrUnavailable, FakeAsrEngine, TranscriptSegment, get_asr_engine


def test_fake_engine_returns_contract_shape():
    engine = FakeAsrEngine()
    out = engine.transcribe(b"fake-audio-bytes", filename="clip.ogg")
    assert out["language"] == "it"
    segs = out["segments"]
    assert len(segs) >= 1
    for s in segs:
        assert isinstance(s["start"], float) and isinstance(s["end"], float)
        assert s["end"] >= s["start"]
        assert s["text"].strip()
        if "confidence" in s:
            assert 0.0 <= s["confidence"] <= 1.0
        # v1: nessun speaker (diarizzazione futura)
        assert "speaker" not in s


def test_fake_engine_is_deterministic():
    a = FakeAsrEngine().transcribe(b"abc", filename="a.ogg")
    b = FakeAsrEngine().transcribe(b"abc", filename="a.ogg")
    assert a == b


def test_factory_returns_fake_by_default_without_deps(monkeypatch):
    monkeypatch.delenv("ML_ASR_ENGINE", raising=False)
    engine = get_asr_engine()
    assert isinstance(engine, FakeAsrEngine)


def test_factory_faster_whisper_missing_raises_honest(monkeypatch):
    monkeypatch.setenv("ML_ASR_ENGINE", "faster_whisper")
    # Simula l'assenza della dipendenza opzionale (installata o meno nel
    # venv): sys.modules['faster_whisper'] = None -> ImportError onesto.
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    try:
        get_asr_engine()
    except AsrUnavailable as exc:
        assert "faster-whisper" in str(exc).lower()
    else:
        raise AssertionError("atteso AsrUnavailable")
