#!/usr/bin/env python3
"""Test di retrieval RAG per i nuovi cataloghi classi/razze/archetipi.

Uso:
  python tools/test_classes_races_retrieval.py

Verifica che le voci di classi, razze e archetipi siano indicizzate e
recuperabili tramite ricerca semantica. Le query troppo corte (es. solo
"Fighter") sono ambigue perché il catalogo contiene migliaia di talenti
che includono quei termini nel nome; per questo il test usa query più
specifiche e, opzionalmente, un filtro per tipo (kind).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer

from src.config import DATA_DIR
from src.rag.retriever import Retriever
from src.rag.store import VectorStore


STORE_DIR = DATA_DIR / "vector_store"
MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# (query, expected_source_prefix, [optional extra expected substring in source])
QUERIES = [
    # classi
    ("Magus class Pathfinder", "reference::classes::Magus", None),
    ("come funziona la classe Magus", "reference::classes::Magus", None),
    ("Fighter class features bonus feats weapon training", "reference::classes::Fighter", None),
    ("caratteristiche del Fighter", "reference::classes::Fighter", None),
    ("Wizard class features arcane bond", "reference::classes::Wizard", None),
    # razze
    ("Human race bonus feat skilled", "reference::races::Human", None),
    ("Elf racial traits low-light vision", "reference::races::Elf", None),
    # archetipi
    ("Magus Kensai archetype weapon focus", "reference::archetypes::", "Kensai"),
    ("Rogue Thug archetype intimidate", "reference::archetypes::", "Thug"),
    ("Fighter Archer archetype ranged combat", "reference::archetypes::", "Archer"),
]


def search_with_kind_filter(retriever, query, kind, top_k=5):
    """Recupera molti risultati e filtra per tipo (classes/races/archetypes).

    Le query corte (es. nome di una classe) competono con migliaia di talenti
    che contengono lo stesso termine; recuperare un campione ampio prima di
    filtrare per kind rende il filtro affidabile.
    """
    results = retriever.search(query, top_k=max(top_k * 20, 200))
    filtered = [r for r in results if r["source"].startswith(f"reference::{kind}::")]
    return filtered[:top_k]


def main():
    store = VectorStore(STORE_DIR)
    if not store.is_ready():
        print(f"ERRORE: indice non trovato in {STORE_DIR}. Esegui prima python tools/index_rag.py")
        return 1

    print(f"Indice pronto: {store.meta.get('count', 0)} chunk")
    print(f"Modello: {MODEL}")
    print("-" * 70)

    encoder = SentenceTransformer(MODEL)
    retriever = Retriever(store, encoder)

    all_ok = True
    for query, expected_prefix, optional_substring in QUERIES:
        results = retriever.search(query, top_k=10)
        found = any(
            r["source"].startswith(expected_prefix)
            and (optional_substring is None or optional_substring in r["source"])
            for r in results
        )
        status = "OK" if found else "FAIL"
        if not found:
            all_ok = False
        print(f"[{status}] Query: {query!r}")
        print(f"       Risultati rilevanti in top-10:")
        relevant = [
            r for r in results
            if r["source"].startswith("reference::classes::")
            or r["source"].startswith("reference::races::")
            or r["source"].startswith("reference::archetypes::")
        ]
        for r in relevant[:3]:
            print(f"         - {r['source']} (score {r['score']:.3f})")
        if not relevant:
            print(f"         Nessun risultato dai nuovi cataloghi in top-10")
        print()

    print("-" * 70)
    print("Test con filtro per tipo (kind):")
    kind_queries = [
        ("Fighter class", "classes", "reference::classes::Fighter"),
        ("Wizard class", "classes", "reference::classes::Wizard"),
        ("Human race", "races", "reference::races::Human"),
        ("Kensai weapon focus magus archetype", "archetypes", "reference::archetypes::Magus (Kensai)"),
        ("Thug rogue archetype", "archetypes", "reference::archetypes::Rogue (Thug)"),
    ]
    for query, kind, expected_source in kind_queries:
        results = search_with_kind_filter(retriever, query, kind, top_k=3)
        found = any(r["source"] == expected_source for r in results)
        status = "OK" if found else "FAIL"
        if not found:
            all_ok = False
        print(f"[{status}] '{query}' filtrato per {kind}: {[r['source'] for r in results]}")

    print("-" * 70)
    if all_ok:
        print("TUTTI I TEST DI RETRIEVAL PASSATI")
        return 0
    print("ALCUNI TEST FALLITI")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
