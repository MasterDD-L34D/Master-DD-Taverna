"""Test del layer RAG."""
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.config import settings
from src.rag.generator import MockProvider, get_provider
from src.rag.indexer import index_modules
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


def test_mock_provider():
    p = MockProvider()
    out = p.generate("qual è il miglior talento?", [{"source": "feats.txt", "text": "Power Attack"}])
    assert "RISPOSTA MOCK" in out
    assert "Power Attack" in out


def test_get_provider():
    assert isinstance(get_provider("mock"), MockProvider)
    # non crasha senza env
    assert isinstance(get_provider(), MockProvider)


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
