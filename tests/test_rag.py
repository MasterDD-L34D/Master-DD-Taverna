"""Test del layer RAG."""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.app import app
from src.config import settings
from src.rag.generator import MockProvider, OllamaOpenAIProvider, OllamaProvider, get_provider
from src.rag.indexer import index_modules, index_reference_catalog
from src.rag.retriever import Retriever
from src.rag.store import VectorStore


@pytest.fixture
def rag_auth():
    original_key = settings.api_key
    original_allow = settings.allow_anonymous
    settings.api_key = "test-rag-key"
    settings.allow_anonymous = False
    yield {"x-api-key": "test-rag-key"}
    settings.api_key = original_key
    settings.allow_anonymous = original_allow


class DummyEncoder:
    """Encoder deterministico per test offline."""

    def __init__(self, dim: int = 32):
        self.dim = dim

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        arr = []
        for t in texts:
            # hash deterministico -> vettore unitario
            h = hash(t) % (2**31)
            np.random.seed(h)
            v = np.random.randn(self.dim).astype(np.float32)
            v = v / np.linalg.norm(v)
            arr.append(v)
        return np.stack(arr)


def test_vector_store_search():
    with tempfile.TemporaryDirectory() as tmp:
        store = VectorStore(tmp)
        chunks = [
            {"id": "a", "source": "mod1.txt", "text": "Pathfinder 1E regole base", "meta": {}},
            {"id": "b", "source": "mod1.txt", "text": "Incantesimi fuoco e ghiaccio", "meta": {}},
        ]
        emb = np.random.randn(2, 16).astype(np.float32)
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        store.save(chunks, emb, "dummy")
        q = np.random.randn(16).astype(np.float32)
        q = q / np.linalg.norm(q)
        results = store.search(q, top_k=2)
        assert len(results) == 2
        assert all("score" in r for r in results)


def test_indexer_and_retriever(tmp_path):
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    (modules_dir / "test.txt").write_text("Pathfinder 1E regole di combattimento.\n\nTalenti e prerequisiti.", encoding="utf-8")

    store_dir = tmp_path / "store"
    store = VectorStore(store_dir)
    encoder = DummyEncoder(dim=16)
    n = index_modules(modules_dir, store, "dummy", encoder)
    assert n >= 1
    assert store.is_ready()

    retriever = Retriever(store, encoder)
    results = retriever.search("combattimento", top_k=3)
    assert len(results) >= 1
    assert any("combattimento" in r["text"].lower() for r in results)


def test_index_reference_catalog_includes_mechanics(tmp_path):
    """Una entry con mechanics produce un chunk contenente il testo "Mechanics:"."""
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "manifest.json").write_text(json.dumps({
        "catalogs": [{"file": "feats.json", "kind": "feats", "is_ogc": True}],
    }), encoding="utf-8")
    (reference_dir / "feats.json").write_text(json.dumps({
        "entries": [{
            "name": "Power Attack",
            "description": "Colpo potente.",
            "mechanics": {"prereq": {"bab": 1}, "effect": "trade attack for damage"},
        }],
    }), encoding="utf-8")

    store = VectorStore(tmp_path / "store")
    encoder = DummyEncoder(dim=16)
    n = index_reference_catalog(reference_dir, store, "dummy", encoder)
    assert n == 1
    text = store.chunks[0]["text"]
    assert "Mechanics:" in text
    assert '"bab": 1' in text


class CountingEncoder(DummyEncoder):
    """DummyEncoder che registra quanti testi encoda a ogni chiamata."""

    def __init__(self, dim: int = 16):
        super().__init__(dim)
        self.encoded: list[str] = []

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        self.encoded.extend(texts)
        return super().encode(texts, **kwargs)


def _write_reference(reference_dir: Path, entries: list[dict]):
    (reference_dir / "manifest.json").write_text(json.dumps({
        "catalogs": [{"file": "feats.json", "kind": "feats", "is_ogc": True}],
    }), encoding="utf-8")
    (reference_dir / "feats.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_incremental_reindex_by_content_hash(tmp_path):
    """Il chunk id e' sha256(source::text)[:16]; una seconda run ri-encoda solo i delta."""
    import hashlib

    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    entries = [
        {"name": "Power Attack", "description": "Colpo potente."},
        {"name": "Dodge", "description": "Schivata."},
    ]
    _write_reference(reference_dir, entries)

    store = VectorStore(tmp_path / "store")
    encoder = CountingEncoder()

    # prima run: tutto da encodare
    assert index_reference_catalog(reference_dir, store, "dummy", encoder) == 2
    assert len(encoder.encoded) == 2

    # id stabile al contenuto, indipendente dalla posizione
    for c in store.chunks:
        expected = hashlib.sha256(f"{c['source']}::{c['text']}".encode("utf-8")).hexdigest()[:16]
        assert c["id"] == expected
    ids_by_source = {c["source"]: c["id"] for c in store.chunks}

    # seconda run senza cambi: 0 da ri-encodare, chunk identici
    encoder.encoded.clear()
    assert index_reference_catalog(reference_dir, store, "dummy", encoder) == 2
    assert encoder.encoded == []
    assert {c["source"]: c["id"] for c in store.chunks} == ids_by_source

    # delta: una entry modificata + una nuova -> solo 2 ri-encodate
    entries[0]["description"] = "Colpo potente migliorato."
    entries.append({"name": "Cleave", "description": "Fendente."})
    _write_reference(reference_dir, entries)
    encoder.encoded.clear()
    assert index_reference_catalog(reference_dir, store, "dummy", encoder) == 3
    assert len(encoder.encoded) == 2
    assert any("migliorato" in t for t in encoder.encoded)
    assert any("Cleave" in t for t in encoder.encoded)
    # la entry invariata mantiene id (embedding riusato)
    assert ids_by_source["reference::feats::Dodge"] in {c["id"] for c in store.chunks}

    # entry rimossa -> il suo id scompare dallo store
    entries.pop(0)
    _write_reference(reference_dir, entries)
    assert index_reference_catalog(reference_dir, store, "dummy", encoder) == 2
    assert not any("Power Attack" in c["source"] for c in store.chunks)


def test_mock_provider():
    p = MockProvider()
    out = p.generate("qual è il miglior talento?", [{"source": "feats.txt", "text": "Power Attack"}])
    assert "RISPOSTA MOCK" in out
    assert "Power Attack" in out


def test_get_provider(monkeypatch):
    # Isola il test da eventuali variabili d'ambiente/.env
    monkeypatch.delenv("RAG_LLM_PROVIDER", raising=False)
    assert isinstance(get_provider("mock"), MockProvider)
    # non crasha senza env
    assert isinstance(get_provider(), MockProvider)


def test_get_provider_ollama():
    p = get_provider("ollama")
    assert isinstance(p, OllamaProvider)
    assert p.model == "qwen2.5-coder:7b"


def test_get_provider_ollama_openai():
    p = get_provider("ollama-openai")
    assert isinstance(p, OllamaOpenAIProvider)
    assert p.model == "qwen2.5-coder:7b"
    assert p.base_url.endswith("/v1")
    # Ollama OpenAI-compatible does not require a real API key
    assert p.api_key is not None


def test_ollama_openai_provider_uses_local_url():
    p = OllamaOpenAIProvider(base_url="http://ollama.local:11434/v1", model="mistral")
    assert p.base_url == "http://ollama.local:11434/v1"
    assert p.model == "mistral"


@pytest.mark.skipif(
    not VectorStore(str(Path(__file__).resolve().parent.parent / "src" / "data" / "vector_store")).is_ready(),
    reason="Indice RAG non trovato; esegui python tools/index_rag.py",
)
def test_rag_search_endpoint(rag_auth):
    with TestClient(app) as client:
        resp = client.post("/rag/search", json={"query": "talento Power Attack", "top_k": 3}, headers=rag_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 3
        assert all("score" in r for r in data["results"])


@pytest.mark.skipif(
    not VectorStore(str(Path(__file__).resolve().parent.parent / "src" / "data" / "vector_store")).is_ready(),
    reason="Indice RAG non trovato; esegui python tools/index_rag.py",
)
def test_rag_ask_endpoint(rag_auth):
    with TestClient(app) as client:
        resp = client.post("/rag/ask", json={"query": "cosa fa Power Attack?", "top_k": 3, "provider": "mock"}, headers=rag_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "RISPOSTA MOCK" in data["answer"]
        assert len(data["results"]) == 3


@pytest.mark.skipif(
    not VectorStore(str(Path(__file__).resolve().parent.parent / "src" / "data" / "vector_store")).is_ready(),
    reason="Indice RAG non trovato; esegui python tools/index_rag.py --include-local",
)
def test_rag_search_includes_local_monsters(rag_auth):
    with TestClient(app) as client:
        # Nome di mostro specifico per evitare competizione con altri cataloghi
        resp = client.post("/rag/search", json={"query": "Aballonian", "top_k": 10}, headers=rag_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert any("reference::monsters" in r["source"] for r in data["results"]), \
            "Nessun mostro locale recuperato; esegui tools/index_rag.py --include-local"
