#!/usr/bin/env python3
"""Test rapido modelli embeddings Ollama con batch piccoli e testi troncati."""
import json
import os
import sys
import time
from pathlib import Path

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / ".." / ".." / "sessione-2026-07-16" / "rapporti" / "ollama_embedding_benchmark.json"
OUT_PATH = Path(OUT_PATH).resolve()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

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


def load_entries():
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
            entries.append({"source": source, "text": text[:2000]})
    return entries


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    norm[norm == 0] = 1
    return vec / norm


def embed_batches(texts: list[str], model: str, batch_size: int = 64):
    embs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = httpx.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": batch, "truncate": True},
            timeout=300,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"batch {i//batch_size} failed: {resp.status_code} {resp.text[:300]}")
        embs.extend(resp.json()["embeddings"])
    return np.array(embs, dtype=np.float32)


def search(query_emb, doc_embs, sources, top_k=5):
    sim = (doc_embs @ query_emb.T).flatten()
    top_idx = np.argsort(sim)[::-1][:top_k]
    return [{"source": sources[i], "score": float(sim[i]), "rank": r + 1} for r, i in enumerate(top_idx)]


def evaluate(model: str, entries: list[dict]):
    print(f"\n=== {model} ===")
    texts = [e["text"] for e in entries]
    sources = [e["source"] for e in entries]
    t0 = time.perf_counter()
    doc_embs = normalize(embed_batches(texts, model))
    indexing_time = time.perf_counter() - t0

    results = []
    for q in QUERIES:
        t0 = time.perf_counter()
        q_emb = normalize(embed_batches([q["text"]], model))[0]
        query_time = time.perf_counter() - t0
        top = search(q_emb, doc_embs, sources)
        target_rank = next((r["rank"] for r in top if r["source"] == q["target"]), None)
        target_score = next((r["score"] for r in top if r["source"] == q["target"]), None)
        results.append({
            "lang": q["lang"], "query": q["text"], "target": q["target"],
            "target_rank": target_rank, "target_score": round(target_score, 4) if target_score else None,
            "top_5": top, "query_time_seconds": round(query_time, 3),
        })
        print(f"  [{q['lang']}] {q['text'][:40]:<40} -> rank={target_rank}")

    mrr = sum(1.0 / r["target_rank"] for r in results if r["target_rank"]) / len(results)
    it_mrr = sum(1.0 / r["target_rank"] for r in results if r["lang"] == "it" and r["target_rank"]) / sum(1 for r in results if r["lang"] == "it")
    en_mrr = sum(1.0 / r["target_rank"] for r in results if r["lang"] == "en" and r["target_rank"]) / sum(1 for r in results if r["lang"] == "en")
    return {
        "model": model, "indexing_time_seconds": round(indexing_time, 2),
        "num_entries": len(entries), "embedding_dim": int(doc_embs.shape[1]),
        "mrr": round(mrr, 4), "mrr_it": round(it_mrr, 4), "mrr_en": round(en_mrr, 4),
        "queries": results,
    }


def main():
    entries = load_entries()
    print(f"Caricate {len(entries)} entry")
    report = {"models": []}
    for model in ["nomic-embed-text:latest", "snowflake-arctic-embed2:568m"]:
        try:
            report["models"].append(evaluate(model, entries))
        except Exception as exc:
            print(f"  ERRORE: {exc}")
            report["models"].append({"model": model, "error": str(exc)})
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSalvato in: {OUT_PATH}")


if __name__ == "__main__":
    main()
