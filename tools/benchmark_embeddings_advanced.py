#!/usr/bin/env python3
"""Benchmark avanzato di modelli embeddings multilingue per RAG Pathfinder.

Estende tools/benchmark_embeddings.py confrontando il modello sentence-transformers
default con modelli multilingue avanzati:

- paraphrase-multilingual-MiniLM-L12-v2 (baseline)
- intfloat/multilingual-e5-large
- BAAI/bge-m3
- sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (opzionale)

Metriche raccolte:
- MRR top-5 su query italiane e inglesi
- MRR per macro-categoria (feats, spells, classes, races, archetypes, items)
- tempo di indicizzazione del catalogo OGC attuale
- dimensione modello su disco (HF cache)
- dimensione vettoriale (embedding_dim)
- numero di entry indicizzate

Il benchmark usa SOLO i cataloghi OGC dichiarati in data/reference/manifest.json,
escludendo pi_local_only/ e materiali non OGC.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
DEFAULT_REPORT_DIR = PROJECT_ROOT / ".." / ".." / "sessione-2026-07-16" / "rapporti"
DEFAULT_JSON = DEFAULT_REPORT_DIR / "embedding_advanced_benchmark.json"
DEFAULT_MD = DEFAULT_REPORT_DIR / "EMBEDDING_ADVANCED_BENCHMARK_2026-07-16.md"

# Query di test italiane e inglesi con target atteso. Coprono feats, spells,
# classes, races, archetypes e items per misurare retrieval cross-lingual su
# tutto il catalogo OGC attuale.
QUERIES = [
    # feats
    {"lang": "it", "category": "feats", "text": "quali sono i prerequisiti del talento Furious Focus", "target": "reference::feats::Furious Focus"},
    {"lang": "it", "category": "feats", "text": "cosa fa il talento Power Attack", "target": "reference::feats::Power Attack"},
    {"lang": "it", "category": "feats", "text": "talento per attacco con due armi", "target": "reference::feats::Two-Weapon Fighting"},
    {"lang": "en", "category": "feats", "text": "prerequisites of Furious Focus", "target": "reference::feats::Furious Focus"},
    {"lang": "en", "category": "feats", "text": "what does Power Attack do", "target": "reference::feats::Power Attack"},
    {"lang": "en", "category": "feats", "text": "two weapon fighting feat", "target": "reference::feats::Two-Weapon Fighting"},
    # spells
    {"lang": "it", "category": "spells", "text": "incantesimo per curare ferite", "target": "reference::spells::Cure Light Wounds"},
    {"lang": "it", "category": "spells", "text": "palla di fuoco pathfinder", "target": "reference::spells::Fireball"},
    {"lang": "en", "category": "spells", "text": "heal wounds spell", "target": "reference::spells::Cure Light Wounds"},
    {"lang": "en", "category": "spells", "text": "fireball spell", "target": "reference::spells::Fireball"},
    # classes
    {"lang": "it", "category": "classes", "text": "come funziona la classe Magus in Pathfinder 1E", "target": "reference::classes::Magus"},
    {"lang": "it", "category": "classes", "text": "classe chierico pathfinder", "target": "reference::classes::Cleric"},
    {"lang": "en", "category": "classes", "text": "how does the Magus class work", "target": "reference::classes::Magus"},
    {"lang": "en", "category": "classes", "text": "Cleric class Pathfinder", "target": "reference::classes::Cleric"},
    # races
    {"lang": "it", "category": "races", "text": "razza elfo pathfinder bonus", "target": "reference::races::Elf"},
    {"lang": "it", "category": "races", "text": "tratti del nano pathfinder", "target": "reference::races::Dwarf"},
    {"lang": "en", "category": "races", "text": "elf race traits Pathfinder", "target": "reference::races::Elf"},
    {"lang": "en", "category": "races", "text": "dwarf racial traits Pathfinder", "target": "reference::races::Dwarf"},
    # archetypes
    {"lang": "it", "category": "archetypes", "text": "archetipo fighter arciere pathfinder", "target": "reference::archetypes::Fighter (Archer)"},
    {"lang": "en", "category": "archetypes", "text": "Fighter Archer archetype Pathfinder", "target": "reference::archetypes::Fighter (Archer)"},
    # items
    {"lang": "it", "category": "items", "text": "amuleto armatura naturale +1", "target": "reference::items::Amulet of Natural Armor +1"},
    {"lang": "en", "category": "items", "text": "amulet of natural armor plus one", "target": "reference::items::Amulet of Natural Armor +1"},
]


def load_reference_entries() -> list[dict]:
    """Carica le entry OGC dal manifest, escludendo PI e non-OGC.

    Ritorna una lista di dict con chiavi 'source' (reference::<kind>::<name>)
    e 'text' (contenuto concatenato per l'embedding).
    """
    manifest_path = REFERENCE_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest non trovato: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    entries: list[dict] = []
    catalogs = manifest.get("catalogs", []) if isinstance(manifest, dict) else []
    for catalog in catalogs:
        if not isinstance(catalog, dict):
            continue
        if not (catalog.get("is_ogc") or catalog.get("cup_allowed")):
            continue
        if catalog.get("is_pi"):
            continue

        rel_path = catalog.get("file", "")
        path = REFERENCE_DIR / rel_path
        if not path.exists():
            continue
        if "pi_local_only" in path.parts:
            continue

        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data.get("entries", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        kind = catalog.get("kind") or path.stem

        for idx, entry in enumerate(items):
            if not isinstance(entry, dict):
                continue
            text_parts = [entry.get("name", "")]
            if "prerequisites" in entry:
                text_parts.append(f"Prerequisiti: {entry['prerequisites']}")
            if "description" in entry:
                text_parts.append(entry["description"])
            elif "short_description" in entry:
                text_parts.append(entry["short_description"])
            if "notes" in entry and entry["notes"]:
                text_parts.append(entry["notes"])
            if "tags" in entry and entry["tags"]:
                text_parts.append("Tags: " + ", ".join(str(t) for t in entry["tags"]))
            text = "\n".join(text_parts)
            if not text.strip():
                continue
            source = f"reference::{kind}::{entry.get('name', idx)}"
            entries.append({"source": source, "text": text})

    return entries


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    norm[norm == 0] = 1
    return vec / norm


def _model_name_to_prefix(model_name: str, mode: str) -> str:
    """Restituisce il prefisso consigliato per modelli E5.

    mode: 'query' o 'document'
    """
    lower = model_name.lower()
    if "e5" in lower:
        return "query: " if mode == "query" else "passage: "
    return ""


def make_sentence_transformers_encoder(
    model_name: str,
    device: str | None = None,
    batch_size: int = 32,
):
    """Costruisce un encoder sentence-transformers con prefissi E5-aware."""
    from sentence_transformers import SentenceTransformer

    kwargs = {}
    if device:
        kwargs["device"] = device
    enc = SentenceTransformer(model_name, **kwargs)

    def _encode(texts: list[str], mode: str = "document") -> np.ndarray:
        prefix = _model_name_to_prefix(model_name, mode)
        if prefix:
            texts = [prefix + t for t in texts]
        return enc.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=batch_size,
        )

    return _encode


def _hf_cache_dir() -> Path:
    """Ritorna la directory cache HF attuale."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        return Path(HF_HUB_CACHE)
    except Exception:
        pass
    fallback = Path.home() / ".cache" / "huggingface" / "hub"
    if fallback.exists():
        return fallback
    return Path.home() / ".cache" / "torch" / "sentence_transformers"


def _model_cache_size_mb(model_name: str) -> float | None:
    """Stima la dimensione su disco del modello nella cache HF."""
    cache = _hf_cache_dir()
    if not cache.exists():
        return None

    # Normalizza il nome per cercare nelle directory cache.
    safe = model_name.replace("/", "--")
    candidates = [d for d in cache.iterdir() if d.is_dir() and safe in d.name]
    if not candidates:
        return None

    total = 0
    for cand in candidates:
        for path in cand.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
    return round(total / (1024 * 1024), 2)


def _load_model_info(model_name: str) -> dict:
    """Raccoglie metadati sul modello (dimensione cache, dimensione embedding)."""
    size_mb = _model_cache_size_mb(model_name)
    return {
        "model": model_name,
        "cache_size_mb": size_mb,
        "cache_size_gb": round(size_mb / 1024, 2) if size_mb else None,
    }


def search(query_emb: np.ndarray, doc_embs: np.ndarray, sources: list[str], top_k: int = 5):
    sim = (doc_embs @ query_emb.T).flatten()
    top_idx = np.argsort(sim)[::-1][:top_k]
    return [
        {"source": sources[i], "score": float(sim[i]), "rank": rank + 1}
        for rank, i in enumerate(top_idx)
    ]


def _mrr(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(1.0 / v for v in valid) / len(values)


def evaluate_model(
    model_name: str,
    encoder_type: str,
    encode_fn: Callable[[list[str], str], np.ndarray],
    entries: list[dict],
    per_query_timeout: float = 120.0,
    max_indexing_time: float | None = None,
) -> dict:
    print(f"\n=== Embeddings: {model_name} ({encoder_type}) ===")
    texts = [e["text"] for e in entries]
    sources = [e["source"] for e in entries]

    info = _load_model_info(model_name)
    print(f"  dimensione cache stimata: {info['cache_size_mb']} MB")

    # Indicizzazione
    t0 = time.perf_counter()
    doc_embs = encode_fn(texts, mode="document")
    doc_embs = normalize(doc_embs)
    indexing_time = time.perf_counter() - t0
    print(f"  tempo indicizzazione: {indexing_time:.2f}s per {len(entries)} entry")

    if max_indexing_time and indexing_time > max_indexing_time:
        raise TimeoutError(f"Indicizzazione troppo lenta: {indexing_time:.2f}s > {max_indexing_time}s")

    results = []
    for q in QUERIES:
        deadline = time.perf_counter() + per_query_timeout
        try:
            q_emb = encode_fn([q["text"]], mode="query")[0]
            query_time = time.perf_counter() - (deadline - per_query_timeout)
        except Exception as exc:
            print(f"  ERRORE encode query [{q['lang']}] {q['text'][:40]}: {exc}")
            results.append({
                "lang": q["lang"],
                "category": q["category"],
                "query": q["text"],
                "target": q["target"],
                "target_rank": None,
                "target_score": None,
                "top_5": [],
                "query_time_seconds": None,
                "error": str(exc),
            })
            continue

        q_emb = q_emb / np.linalg.norm(q_emb)
        top = search(q_emb, doc_embs, sources, top_k=5)
        target_rank = next((r["rank"] for r in top if r["source"] == q["target"]), None)
        target_score = next((r["score"] for r in top if r["source"] == q["target"]), None)
        results.append({
            "lang": q["lang"],
            "category": q["category"],
            "query": q["text"],
            "target": q["target"],
            "target_rank": target_rank,
            "target_score": round(target_score, 4) if target_score else None,
            "top_5": top,
            "query_time_seconds": round(query_time, 3),
        })
        status = f"rank={target_rank}" if target_rank else "MISS"
        print(f"  [{q['lang']}] {q['text'][:45]:<45} -> {status}")

    mrr_overall = _mrr([r["target_rank"] for r in results])
    mrr_it = _mrr([r["target_rank"] for r in results if r["lang"] == "it"])
    mrr_en = _mrr([r["target_rank"] for r in results if r["lang"] == "en"])

    by_category: dict[str, list[int | None]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["target_rank"])
    category_mrr = {cat: _mrr(ranks) for cat, ranks in by_category.items()}

    return {
        "model": model_name,
        "encoder_type": encoder_type,
        "indexing_time_seconds": round(indexing_time, 2),
        "num_entries": len(entries),
        "embedding_dim": int(doc_embs.shape[1]),
        "cache_size_mb": info["cache_size_mb"],
        "cache_size_gb": info["cache_size_gb"],
        "mrr": round(mrr_overall, 4) if mrr_overall is not None else None,
        "mrr_it": round(mrr_it, 4) if mrr_it is not None else None,
        "mrr_en": round(mrr_en, 4) if mrr_en is not None else None,
        "mrr_by_category": {k: round(v, 4) if v is not None else None for k, v in category_mrr.items()},
        "queries": results,
    }


def _build_markdown(report: dict, args: argparse.Namespace) -> str:
    """Genera il report Markdown a partire dal JSON del benchmark."""
    lines = [
        "# Benchmark embeddings multilingue avanzati — 2026-07-16",
        "",
        "> Confronto tra modelli di embedding multilingue per il retrieval RAG del catalogo OGC Pathfinder 1E.",
        "",
        "## Ambiente",
        "",
        f"- **Repository:** `{PROJECT_ROOT}`",
        f"- **Catalogo reference:** `{REFERENCE_DIR}`",
        f"- **Device:** CPU (`torch` installato in versione CPU-only)",
        f"- **Modelli testati:** {', '.join(m['model'] for m in report['models'] if 'error' not in m)}",
        f"- **Numero di query:** {len(report.get('queries', QUERIES))} ({sum(1 for q in QUERIES if q['lang'] == 'it')} IT, {sum(1 for q in QUERIES if q['lang'] == 'en')} EN)",
        f"- **Entry indicizzate:** {report.get('num_entries', 'N/A')}",
        "",
        "## Comandi eseguiti",
        "",
        "```bash",
        f"cd {PROJECT_ROOT}",
        f".venv/Scripts/python tools/benchmark_embeddings_advanced.py --json {args.json} --md {args.md}",
        "```",
        "",
        "## Risultati aggregate",
        "",
        "| Modello | Tipo | Dim. cache (GB) | Dim. embedding | Tempo indicizz. (s) | MRR | MRR IT | MRR EN |",
        "|---------|------|-----------------|----------------|---------------------|-----|--------|--------|",
    ]
    for m in report["models"]:
        if "error" in m:
            lines.append(
                f"| {m['model']} | {m.get('encoder_type', 'N/A')} | — | — | — | **ERRORE:** {m['error']} | — | — |"
            )
            continue
        lines.append(
            f"| {m['model']} | {m['encoder_type']} | {m.get('cache_size_gb', 'N/A')} | "
            f"{m.get('embedding_dim', 'N/A')} | {m.get('indexing_time_seconds', 'N/A')} | "
            f"{m.get('mrr', 'N/A')} | {m.get('mrr_it', 'N/A')} | {m.get('mrr_en', 'N/A')} |"
        )

    lines.extend([
        "",
        "### MRR per categoria",
        "",
    ])

    # Tabella pivot modello x categoria
    categories = sorted({cat for m in report["models"] if "mrr_by_category" in m for cat in m["mrr_by_category"]})
    if categories:
        header = "| Modello | " + " | ".join(categories) + " |"
        sep = "|" + "|".join(["---"] * (1 + len(categories))) + "|"
        lines.extend([header, sep])
        for m in report["models"]:
            if "mrr_by_category" not in m:
                continue
            row = f"| {m['model']} |"
            for cat in categories:
                row += f" {m['mrr_by_category'].get(cat, 'N/A')} |"
            lines.append(row)
        lines.append("")

    lines.extend([
        "## Dettaglio per modello",
        "",
    ])

    for m in report["models"]:
        lines.append(f"### {m['model']}")
        if "error" in m:
            lines.extend([f"- **Errore:** {m['error']}", ""])
            continue
        lines.extend([
            f"- **Encoder:** {m['encoder_type']}",
            f"- **Dimensione cache:** {m.get('cache_size_gb', 'N/A')} GB ({m.get('cache_size_mb', 'N/A')} MB)",
            f"- **Dimensione embedding:** {m.get('embedding_dim', 'N/A')}",
            f"- **Tempo indicizzazione:** {m.get('indexing_time_seconds', 'N/A')} s",
            f"- **MRR complessivo:** {m.get('mrr', 'N/A')}",
            f"- **MRR IT:** {m.get('mrr_it', 'N/A')}",
            f"- **MRR EN:** {m.get('mrr_en', 'N/A')}",
            "",
            "| Lingua | Categoria | Query | Rank target | Score target |",
            "|--------|-----------|-------|-------------|--------------|",
        ])
        for q in m.get("queries", []):
            rank = q.get("target_rank")
            score = q.get("target_score")
            lines.append(
                f"| {q['lang']} | {q['category']} | {q['query']} | "
                f"{rank if rank is not None else 'MISS'} | "
                f"{score if score is not None else '—'} |"
            )
        lines.append("")

    lines.extend([
        "## Osservazioni",
        "",
        "- I modelli E5 usano i prefissi ufficiali `query:` e `passage:` rispettivamente per query e documenti; gli altri modelli non usano prefissi.",
        "- Il benchmark è eseguito su CPU; i tempi di indicizzazione su GPU sarebbero significativamente inferiori.",
        "- I cataloghi OGC usati sono quelli dichiarati in `data/reference/manifest.json`; `pi_local_only/` è escluso.",
        "- Eventuali modelli marcati come ERRORE non sono stati valutati (timeout, spazio insufficiente o problema di download/caricamento).",
        "",
        "## Prossimi passi",
        "",
        "1. Se i modelli più grandi (in particolare `BAAI/bge-m3`) falliscono per timeout su CPU, ripetere il benchmark su workstation con GPU per ottenere tempi realistici.",
        "2. Valutare il trade-off MRR vs. latenza query per scegliere il modello da usare in produzione; il default `paraphrase-multilingual-MiniLM-L12-v2` resta la scelta conservativa per bassa latenza.",
        "3. Se il modello vincitore in MRR introduce latenza eccessiva, considerare un indice ibrido (BM25 + embedding) o quantizzazione.",
        "4. Aggiornare `src/config.py` e `.env.example` con il modello embedding scelto solo dopo approvazione esplicita.",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Benchmark embeddings multilingue avanzati")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="Path output JSON")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD, help="Path output Markdown")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "paraphrase-multilingual-MiniLM-L12-v2",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            "intfloat/multilingual-e5-large",
            "BAAI/bge-m3",
        ],
        help="Modelli sentence-transformers da confrontare",
    )
    parser.add_argument(
        "--max-indexing-time",
        type=float,
        default=None,
        help="Timeout massimo per l'indicizzazione di un singolo modello (secondi)",
    )
    parser.add_argument(
        "--per-query-timeout",
        type=float,
        default=120.0,
        help="Timeout per l'encoding di una singola query (secondi)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device per SentenceTransformer (es. 'cpu', 'cuda'). Default: auto.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size per l'encoding (default 32, utile aumentarlo su CPU per modelli grandi).",
    )
    args = parser.parse_args()

    args.json = args.json.resolve()
    args.md = args.md.resolve()

    entries = load_reference_entries()
    print(f"Caricate {len(entries)} entry OGC da {REFERENCE_DIR}")

    report = {
        "reference_dir": str(REFERENCE_DIR),
        "num_entries": len(entries),
        "models": [],
        "queries": QUERIES,
    }

    for model_name in args.models:
        try:
            encoder = make_sentence_transformers_encoder(
                model_name, device=args.device, batch_size=args.batch_size
            )
            result = evaluate_model(
                model_name,
                "sentence-transformers",
                encoder,
                entries,
                per_query_timeout=args.per_query_timeout,
                max_indexing_time=args.max_indexing_time,
            )
            report["models"].append(result)
        except Exception as exc:
            print(f"  ERRORE con {model_name}: {exc}")
            report["models"].append({
                "model": model_name,
                "encoder_type": "sentence-transformers",
                "error": str(exc),
            })

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)

    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport JSON salvato in: {args.json}")

    md_content = _build_markdown(report, args)
    args.md.write_text(md_content, encoding="utf-8")
    print(f"Report Markdown salvato in: {args.md}")


if __name__ == "__main__":
    main()
