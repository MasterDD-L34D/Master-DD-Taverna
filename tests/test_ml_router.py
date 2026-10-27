"""Test per src/ml/router.py + storage WORM (REF-09 v1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from src.ml.storage import save_audio_worm


def test_worm_storage_dedup_immutable(tmp_path):
    p1, sha1 = save_audio_worm(b"audio-bytes", "clip.ogg", tmp_path)
    p2, sha2 = save_audio_worm(b"audio-bytes", "clip.ogg", tmp_path)
    assert sha1 == sha2 and p1 == p2
    assert len(list(tmp_path.iterdir())) == 1  # nessuna riscrittura
    p3, sha3 = save_audio_worm(b"altri-bytes", "clip.ogg", tmp_path)
    assert sha3 != sha1 and p3 != p1


def test_transcribe_endpoint_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("ML_ASR_ENGINE", "fake")
    monkeypatch.setenv("ML_AUDIO_DIR", str(tmp_path))
    from src.app import app

    client = TestClient(app)
    resp = client.post(
        "/ml/transcribe", files={"file": ("clip.ogg", b"audio-finto", "audio/ogg")}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["language"] == "it"
    assert len(data["segments"]) >= 1
    seg = data["segments"][0]
    assert {"start", "end", "text"} <= set(seg)
    assert seg["end"] >= seg["start"]
    # WORM: l'audio e' persistito
    assert len(list(tmp_path.iterdir())) == 1


def test_transcribe_engine_unavailable_is_honest_501(monkeypatch, tmp_path):
    monkeypatch.setenv("ML_ASR_ENGINE", "faster_whisper")
    # Simula l'assenza della dipendenza opzionale (indipendente dal venv):
    # sys.modules['faster_whisper'] = None -> ImportError -> 501 onesto.
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.setenv("ML_AUDIO_DIR", str(tmp_path))
    from src.app import app

    client = TestClient(app)
    resp = client.post(
        "/ml/transcribe", files={"file": ("clip.ogg", b"audio-finto", "audio/ogg")}
    )
    assert resp.status_code == 501
    assert "faster-whisper" in resp.json()["detail"].lower()


def test_transcribe_diarize_fake_engine(monkeypatch, tmp_path):
    """diarize=true (form field): i segmenti hanno la chiave speaker."""
    monkeypatch.setenv("ML_ASR_ENGINE", "fake")
    monkeypatch.setenv("ML_AUDIO_DIR", str(tmp_path))
    from src.app import app

    client = TestClient(app)
    resp = client.post(
        "/ml/transcribe",
        files={"file": ("clip.ogg", b"audio-finto", "audio/ogg")},
        data={"diarize": "true"},
    )
    assert resp.status_code == 200
    speakers = [s["speaker"] for s in resp.json()["segments"]]
    assert speakers == ["S1", "S2"]
    # default (senza il flag): niente chiave speaker
    resp2 = client.post(
        "/ml/transcribe", files={"file": ("clip2.ogg", b"audio-finto", "audio/ogg")}
    )
    assert all("speaker" not in s for s in resp2.json()["segments"])
