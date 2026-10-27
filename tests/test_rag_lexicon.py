"""Test per le mitigazioni retrieval (finding RAG eval 2026-07-25):

1. query-translation IT->EN con lessico da data/it_en_lexicon.json;
2. fast-path esatto per nome proprio (embedding debole su nomi inventati).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.lexicon import load_lexicon, translate_query
from src.rag.retriever import Retriever
from src.rag.store import VectorStore
from src.rag.indexer import index_reference_catalog


class DummyEncoder:
    """Encoder deterministico: stesso vettore per ogni input (il ranking
    dipende solo dai boost, mai dal contenuto semantico)."""

    def __init__(self, dim=16):
        self.dim = dim

    def encode(self, texts, show_progress_bar=False, convert_to_numpy=True):
        import numpy as np

        if isinstance(texts, str):
            return np.ones(self.dim) / self.dim**0.5
        return np.array([np.ones(self.dim) / self.dim**0.5 for _ in texts])


def _make_store(tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "manifest.json").write_text(
        json.dumps(
            {
                "catalogs": [{"file": "races.json", "kind": "races", "is_ogc": True}],
            }
        ),
        encoding="utf-8",
    )
    (reference_dir / "races.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"name": "Aasimar", "description": "Modificatori razziali."},
                    {"name": "Dwarf", "description": "Tratti nanici."},
                ],
            }
        ),
        encoding="utf-8",
    )
    store = VectorStore(tmp_path / "store")
    index_reference_catalog(reference_dir, store, "dummy", DummyEncoder())
    return store


def test_translate_query_applica_lessico(tmp_path):
    lexicon_file = tmp_path / "lex.json"
    lexicon_file.write_text(
        json.dumps(
            {"attacco poderoso": "power attack", "cotta di maglia": "chainmail"}
        ),
        encoding="utf-8",
    )
    lex = load_lexicon(lexicon_file)
    out = translate_query("cosa fa il talento Attacco Poderoso?", lex)
    assert "power attack" in out.lower()
    # case preservato fuori dai termini tradotti
    assert "cosa fa" in out


def test_translate_query_lessico_assente_e_neutro(tmp_path):
    lex = load_lexicon(tmp_path / "non_esiste.json")
    assert lex == {}
    assert translate_query("qualunque cosa", lex) == "qualunque cosa"


def test_fast_path_nome_esatto_batte_embedding_debole(tmp_path):
    """'Aasimar' (nome inventato, embedding debole) deve arrivare primo
    anche senza segnale semantico (encoder piatto)."""
    store = _make_store(tmp_path)
    retriever = Retriever(store, DummyEncoder())
    results = retriever.search("aasimar", top_k=2)
    assert results[0]["source"].endswith("::Aasimar")


def test_fast_path_token_nome_nella_frase(tmp_path):
    """Un token della query che e' esattamente un nome di entry vince."""
    store = _make_store(tmp_path)
    retriever = Retriever(store, DummyEncoder())
    results = retriever.search("modificatori razziali aasimar", top_k=2)
    assert results[0]["source"].endswith("::Aasimar")
