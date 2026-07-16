#!/usr/bin/env python3
"""Benchmark modelli di embeddings per retrieval cross-lingual RAG.

Confronta il modello sentence-transformers attuale con modelli Ollama
embeddings su query italiane e inglesi contro il catalogo reference.
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / ".." / ".." / "sessione-2026-07-16" / "rapporti" / "embedding_benchmark.json"
OUT_PATH = Path(OUT_PATH).resolve()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Domande di test (italiano e inglese) con target atteso
QUERIES = [
    {"lang": "it", "text": "quali sono i prerequisiti del talento Furious Focus", "target": "reference::feats::Furious Focus"},
    {"lang": "it", "text": "cosa fa il talento Power Attack", "target": "reference::feats::Power Attack"},
    {"lang": "it", "text": "talento per attacco con due armi", "target": "reference::feats::Two-Weapon Fighting"},
    {"lang": "it", "text": "incantesimo per curare ferite", "target": "reference::spells::Cure Light Wounds"},
    {"lang": "en", "text": "prerequisites of Furious Focus", "target": "reference::feats::Furious Focus"},
    {"lang": "en", "text": "what does Power Attack do", "target": "reference::feats::Power Attack"},
    {"lang": "en", "text": "two weapon fighting feat", "target": "reference::feats::Two-Weapon Fighting"},
    {"lang": "en", "text": "heal wounds spell", "target": "reference::spells::Cure Light Wounds"},
]


def load_reference_entries():
    """Load all reference entries as {source: text}."""
    entries = []
    for path in sorted(REFERENCE_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        data = json.load(open(path, encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("entries", [])
        kind = path.stem
        for entry in items:
            text_parts = [entry.get("name", "")]
            if "prerequisites" in entry:
                text_parts.append(f"Prerequisiti: {entry['prerequisites']}")
            if "description" in entry:
                text_parts.append(entry["description"])
            elif "short_description" in entry:
                text_parts.append(entry["short_description"])
            text = "\n".join(text_parts)
            if not text.strip():
                continue
            source = f"reference::{kind}::{entry.get('name', '')}"
            entries.append({"source": source, "text": text})
    return entries


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    norm[norm == 0] = 1
    return vec / norm


def make_ollama_encoder(model: str):
    """Return an encoder function backed by Ollama /api/embed (batch)."""
    def _encode(texts: list[str]) -> np.ndarray:
        # Truncate aggressively: Ollama embedding models have limited context
        # and some do not honour the truncate flag for very long inputs.
        truncated = [t[:2000] for t in texts]
        resp = httpx.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": truncated, "truncate": True},
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        return np.array(data["embeddings"], dtype=np.float32)
    return _encode


def make_sentence_transformers_encoder(model: str):
    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer(model)
    def _encode(texts: list[str]) -> np.ndarray:
        return enc.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return _encode


def search(query_emb: np.ndarray, doc_embs: np.ndarray, sources: list[str], top_k: int = 5):
    sim = (doc_embs @ query_emb.T).flatten()
    top_idx = np.argsort(sim)[::-1][:top_k]
    return [
        {"source": sources[i], "score": float(sim[i]), "rank": rank + 1}
        for rank, i in enumerate(top_idx)
    ]


def evaluate_model(model_name: str, encoder_type: str, encode_fn, entries: list[dict]):
    print(f"\n=== Embeddings: {model_name} ({encoder_type}) ===")
    texts = [e["text"] for e in entries]
    sources = [e["source"] for e in entries]

    t0 = time.perf_counter()
    doc_embs = encode_fn(texts)
    doc_embs = normalize(doc_embs)
    indexing_time = time.perf_counter() - t0

    results = []
    for q in QUERIES:
        t0 = time.perf_counter()
        q_emb = encode_fn([q["text"]])[0]
        query_time = time.perf_counter() - t0
        q_emb = q_emb / np.linalg.norm(q_emb)

        top = search(q_emb, doc_embs, sources, top_k=5)
        target_rank = next((r["rank"] for r in top if r["source"] == q["target"]), None)
        target_score = next((r["score"] for r in top if r["source"] == q["target"]), None)
        results.append({
            "lang": q["lang"],
            "query": q["text"],
            "target": q["target"],
            "target_rank": target_rank,
            "target_score": round(target_score, 4) if target_score else None,
            "top_5": top,
            "query_time_seconds": round(query_time, 3),
        })
        status = f"rank={target_rank}" if target_rank else "MISS"
        print(f"  [{q['lang']}] {q['text'][:40]:<40} -> {status}")

    mrr = sum(1.0 / r["target_rank"] for r in results if r["target_rank"]) / len(results)
    it_mrr = sum(1.0 / r["target_rank"] for r in results if r["lang"] == "it" and r["target_rank"]) / sum(1 for r in results if r["lang"] == "it")
    en_mrr = sum(1.0 / r["target_rank"] for r in results if r["lang"] == "en" and r["target_rank"]) / sum(1 for r in results if r["lang"] == "en")

    return {
        "model": model_name,
        "encoder_type": encoder_type,
        "indexing_time_seconds": round(indexing_time, 2),
        "num_entries": len(entries),
        "embedding_dim": int(doc_embs.shape[1]),
        "mrr": round(mrr, 4),
        "mrr_it": round(it_mrr, 4),
        "mrr_en": round(en_mrr, 4),
        "queries": results,
    }


def main():
    entries = load_reference_entries()
    print(f"Caricate {len(entries)} entry reference da {REFERENCE_DIR}")

    report = {
        "ollama_url": OLLAMA_URL,
        "reference_dir": str(REFERENCE_DIR),
        "models": [],
    }

    # Modello attuale (sentence-transformers)
    report["models"].append(evaluate_model(
        "paraphrase-multilingual-MiniLM-L12-v2",
        "sentence-transformers",
        make_sentence_transformers_encoder("paraphrase-multilingual-MiniLM-L12-v2"),
        entries,
    ))

    # Modelli embeddings Ollama disponibili
    for ollama_model in ["nomic-embed-text:latest", "snowflake-arctic-embed2:568m"]:
        try:
            report["models"].append(evaluate_model(
                ollama_model, "ollama", make_ollama_encoder(ollama_model), entries
            ))
        except Exception as exc:
            print(f"  ERRORE con {ollama_model}: {exc}")
            report["models"].append({
                "model": ollama_model,
                "encoder_type": "ollama",
                "error": str(exc),
            })

    # Prova mpnet multilingue se riesce a scaricarsi entro i tempi
    try:
        report["models"].append(evaluate_model(
            "paraphrase-multilingual-mpnet-base-v2",
            "sentence-transformers",
            make_sentence_transformers_encoder("paraphrase-multilingual-mpnet-base-v2"),
            entries,
        ))
    except Exception as exc:
        print(f"  ERRORE con paraphrase-multilingual-mpnet-base-v2: {exc}")
        report["models"].append({
            "model": "paraphrase-multilingual-mpnet-base-v2",
            "encoder_type": "sentence-transformers",
            "error": str(exc),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport salvato in: {OUT_PATH}")


if __name__ == "__main__":
    main()
