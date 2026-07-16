"""Test del Build Agent."""
import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.config import settings
from src.agents.builder import generate_build, _build_fallback, _find_reference_entries
from src.rag.store import VectorStore
from pathlib import Path


def test_find_reference_entries():
    refs = _find_reference_entries("Power Attack fighter", Path("data/reference"), top_k=5)
    assert len(refs) <= 5
    # almeno un feat dovrebbe contenere power attack
    names = [r["name"].lower() for r in refs]
    assert any("power" in n for n in names)


def test_build_fallback():
    request = {"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR"}
    refs = [{"source_id": "power_attack", "type": "feat", "name": "Power Attack"}]
    payload = _build_fallback(request, refs)
    assert payload["build_state"]["class"] == "Fighter"
    assert payload["reference_catalog_version"] == "2026.04.03"
    assert payload["step_audit"]["client_fingerprint_hash"]


def test_generate_build_mock():
    request = {"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR"}
    payload = generate_build(request, retriever=None, provider_name="mock")
    assert payload["build_state"]["class"] == "Fighter"
    assert payload["benchmark"]["meta_tier"]


@pytest.mark.skipif(
    not VectorStore(str(Path(__file__).resolve().parent.parent / "src" / "data" / "vector_store")).is_ready(),
    reason="Indice RAG non trovato; esegui python tools/index_rag.py",
)
def test_rag_build_endpoint():
    original_key = settings.api_key
    original_allow = settings.allow_anonymous
    try:
        settings.api_key = "test-build-key"
        settings.allow_anonymous = False
        headers = {"x-api-key": "test-build-key"}
        with TestClient(app) as client:
            resp = client.post(
                "/rag/build",
                json={"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR", "provider": "mock"},
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "build" in data
            assert data["build"]["build_state"]["class"] == "Fighter"
    finally:
        settings.api_key = original_key
        settings.allow_anonymous = original_allow
