#!/usr/bin/env python3
"""Costruisce l'indice RAG per moduli e catalogo reference.

Uso:
  python tools/index_rag.py

Legge src/modules/ e data/reference/*.json, genera embeddings con
sentence-transformers e li salva in data/vector_store/.
"""
import os
import sys
from pathlib import Path

# allow importing src.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer

from src.config import MODULES_DIR, DATA_DIR
from src.rag.indexer import index_modules, index_reference_catalog
from src.rag.store import VectorStore


ROOT_DIR = Path(__file__).resolve().parent.parent


def main():
    model = os.getenv("RAG_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    print(f"Caricamento modello embeddings: {model}")
    encoder = SentenceTransformer(model)

    store_dir = Path(os.getenv("RAG_STORE_DIR", str(DATA_DIR / "vector_store")))
    store = VectorStore(store_dir)

    print(f"Indicizzazione moduli da: {MODULES_DIR}")
    n_modules = index_modules(MODULES_DIR, store, model, encoder)
    print(f"  chunk moduli indicizzati: {n_modules}")

    ref_dir = ROOT_DIR / "data" / "reference"
    print(f"Indicizzazione catalogo reference da: {ref_dir}")
    n_ref = index_reference_catalog(ref_dir, store, model, encoder)
    print(f"  chunk reference indicizzati: {n_ref}")

    print(f"Indice salvato in: {store_dir}")
    print(f"Totale chunk: {store.meta.get('count', 0)}")


if __name__ == "__main__":
    main()
