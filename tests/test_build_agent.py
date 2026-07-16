"""Test del Build Agent."""
import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.config import settings
from src.agents.builder import (
    generate_build,
    _build_fallback,
    _find_reference_entries,
    _validate_catalog_references,
    _validate_numerical_constraints,
    _reference_dir,
)
from src.agents.builder_benchmarks import compute_benchmarks, evaluate_build
from src.rag.store import VectorStore
from pathlib import Path


def test_find_reference_entries():
    ref_dir = _reference_dir()
    refs = _find_reference_entries("Power Attack fighter", ref_dir, top_k=5)
    assert len(refs) <= 5
    # almeno un feat dovrebbe contenere power attack
    names = [r["name"].lower() for r in refs]
    assert any("power" in n for n in names)


def test_benchmarks_level_5():
    b = compute_benchmarks(5, "DPR")
    assert b["monster"]["hp"] == 55
    assert b["monster"]["ac"] == 18
    # Bench-Pressing: attack green = AC - 7 = 11
    assert b["attack"]["green"] == 11
    # DPR green = 25% HP = 13.75
    assert abs(b["dpr"]["green"] - 13.75) < 0.01
    # AC green = low_atk + 15 = 22
    assert b["ac"]["green"] == 22


def test_evaluate_build_tiers():
    b = compute_benchmarks(5, "DPR")
    # Statistiche green DPR
    stats = {"PF": 50, "CA": 22, "DPR": 15, "saves": {"Tempra": 8, "Riflessi": 4, "Volonta": 4}}
    ev = evaluate_build(stats, b, "DPR")
    assert ev["meta_tier"] in {"T1", "T2", "T3"}
    assert ev["metrics"]["DPR"]["tier"] in {"blue", "green"}


def test_validate_catalog_references_ok():
    ref_dir = _reference_dir()
    payload = {
        "catalog_references": [
            {"source_id": "feats:power_attack", "type": "feat", "name": "Power Attack"}
        ]
    }
    errors = _validate_catalog_references(payload, ref_dir)
    assert errors == []


def test_validate_catalog_references_missing():
    ref_dir = _reference_dir()
    payload = {
        "catalog_references": [
            {"source_id": "nonexistent:foo", "type": "feat", "name": "Foo"}
        ]
    }
    errors = _validate_catalog_references(payload, ref_dir)
    assert any("non trovata" in e for e in errors)


def test_validate_numerical_constraints():
    payload = {
        "request": {"level": 5, "focus": "DPR"},
        "benchmark": {"statistics": {"PF": 1000, "CA": 50, "DPR": 500, "saves": {"Tempra": -10, "Riflessi": 0, "Volonta": 0}}},
    }
    errors = _validate_numerical_constraints(payload)
    assert any("PF irrealisticamente alto" in e for e in errors)
    assert any("CA irrealistica" in e for e in errors)
    assert any("DPR irrealistico" in e for e in errors)
    assert any("Tempra" in e and "irrealistico" in e for e in errors)


def test_build_fallback():
    request = {"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR"}
    refs = [{"source_id": "feats:power_attack", "type": "feat", "name": "Power Attack"}]
    payload = _build_fallback(request, refs)
    assert payload["build_state"]["class"] == "Fighter"
    assert payload["reference_catalog_version"] == "2026.04.03"
    assert payload["step_audit"]["client_fingerprint_hash"]
    assert "benchmark_evaluation" in payload
    assert payload["benchmark"]["statistics"]["DPR"] >= 13.75


def test_generate_build_mock():
    request = {"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR"}
    payload = generate_build(request, retriever=None, provider_name="mock")
    assert payload["build_state"]["class"] == "Fighter"
    assert payload["benchmark"]["meta_tier"]
    assert "benchmark_evaluation" in payload


@pytest.mark.parametrize("cls,focus", [
    ("Fighter", "DPR"),
    ("Fighter", "tank"),
    ("Wizard", "control"),
    ("Cleric", "support"),
    ("Rogue", "DPR"),
])
def test_generate_build_mock_variants(cls, focus):
    request = {"class": cls, "race": "Human", "level": 5, "focus": focus}
    payload = generate_build(request, retriever=None, provider_name="mock")
    assert payload["build_state"]["class"] == cls
    assert payload["validation_status"] == "passed"
    assert payload["benchmark_evaluation"]["meta_tier"] in {"T1", "T2", "T3", "T4"}


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
            assert "benchmark_evaluation" in data["build"]
    finally:
        settings.api_key = original_key
        settings.allow_anonymous = original_allow
