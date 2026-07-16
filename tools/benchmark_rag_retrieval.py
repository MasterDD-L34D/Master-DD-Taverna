#!/usr/bin/env python3
"""Benchmark rapido per il retrieval RAG su reference PF1e.

Uso:
    python tools/benchmark_rag_retrieval.py \
        --query "cosa fa Power Attack?" \
        --query "Fireball" \
        --query "Furious Focus" \
        --top-k 5

Salva/legge un file JSON con i risultati per confronto prima/dopo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sentence_transformers import SentenceTransformer

from src.rag.retriever import Retriever
from src.rag.store import VectorStore


DEFAULT_QUERIES = [
    "cosa fa il talento Power Attack in Pathfinder 1E?",
    "Fireball incantesimo Pathfinder 1E",
    "quali sono i prerequisiti di Furious Focus?",
    "Amulet of Natural Armor oggetto magico",
    "come funziona il talento Cleave?",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark retrieval RAG")
    parser.add_argument(
        "--store-dir",
        default=str(ROOT_DIR / "src" / "data" / "vector_store"),
        help="Directory del vector store",
    )
    parser.add_argument(
        "--model",
        default="paraphrase-multilingual-MiniLM-L12-v2",
        help="Modello sentence-transformers",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Query da eseguire (ripetibile); default interno se omesso",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Numero di chunk da recuperare",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="File JSON su cui scrivere i risultati",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="File JSON di risultati precedenti da confrontare",
    )
    parser.add_argument(
        "--filter-source",
        default="reference::",
        help="Filtra i risultati per prefisso source (default 'reference::')",
    )
    parser.add_argument(
        "--filter-source-regex",
        help="Filtra i risultati con regex sul source (es. 'reference::(feats|spells|items)::')",
    )
    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES

    print(f"Caricamento vector store: {args.store_dir}")
    store = VectorStore(args.store_dir)
    if not store.is_ready():
        print("ERRORE: vector store non inizializzato. Esegui prima python tools/index_rag.py", file=sys.stderr)
        sys.exit(1)

    print(f"Caricamento modello embeddings: {args.model}")
    encoder = SentenceTransformer(args.model)
    retriever = Retriever(store, encoder)

    results: list[dict] = []
    for query in queries:
        print(f"\nQuery: {query}")
        hits = retriever.search(query, top_k=args.top_k * 3)
        if args.filter_source_regex:
            import re

            rx = re.compile(args.filter_source_regex)
            hits = [h for h in hits if rx.search(h["source"])]
        elif args.filter_source:
            hits = [h for h in hits if h["source"].startswith(args.filter_source)]
        hits = hits[: args.top_k]

        summary = {
            "query": query,
            "top_k": args.top_k,
            "hits": [
                {
                    "source": h["source"],
                    "score": round(h["score"], 4),
                    "text_preview": h["text"][:200].replace("\n", " "),
                }
                for h in hits
            ],
        }
        results.append(summary)
        for i, h in enumerate(hits, 1):
            print(f"  {i}. {h['source']} [{h['score']:.4f}]")
            print(f"     {h['text'][:160].replace(chr(10), ' ')}")

    report = {"queries": results, "model": args.model, "store_count": store.meta.get("count", 0)}

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nRisultati salvati in: {args.output}")

    if args.input and args.input.exists():
        previous = json.loads(args.input.read_text(encoding="utf-8"))
        print("\n=== Confronto con precedente ===")
        for prev, curr in zip(previous.get("queries", []), results):
            prev_best = prev["hits"][0]["score"] if prev["hits"] else 0.0
            curr_best = curr["hits"][0]["score"] if curr["hits"] else 0.0
            delta = curr_best - prev_best
            sign = "+" if delta >= 0 else ""
            print(
                f"{curr['query'][:50]:<50}  top-1: {prev_best:.4f} -> {curr_best:.4f} "
                f"({sign}{delta:.4f})"
            )


if __name__ == "__main__":
    main()
