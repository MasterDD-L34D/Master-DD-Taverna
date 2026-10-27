#!/usr/bin/env python3
"""RAG eval — valutazione GENERAZIONE (2026-07-25, punto 8 coda).

Per ogni domanda del question set: retrieval reale (retriever di produzione,
con query-translation integrata) -> generazione col provider configurato
(default: RAG_LLM_PROVIDER da .env) -> rubriche deterministiche
(`expect_all` = tutte le stringhe presenti; `expect_any` = almeno una).

Misura la qualita' della risposta finale del Master in italiano. NON usa
LLM-judge (decisione grill: rubriche deterministiche ora, giudice in futuro).

La misura e' non deterministica (varianza osservata 78-94% tra run): con
`--runs N` ogni domanda viene generata N volte e passa a voto di maggioranza
(B2, coda 2026-07-25). Default 3 run per una misura stabile.

Uso:
    .venv/Scripts/python tools/eval_rag_generation.py              # report a video (3 run/domanda)
    .venv/Scripts/python tools/eval_rag_generation.py --runs 1     # passata singola veloce
    .venv/Scripts/python tools/eval_rag_generation.py --write      # salva reports/rag_generation_report.json
    .venv/Scripts/python tools/eval_rag_generation.py --only feat-power-attack,equip-chainmail
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUESTIONS_PATH = ROOT / "data" / "rag_eval_questions.json"
REPORT_PATH = ROOT / "reports" / "rag_generation_report.json"


def _check(answer: str, q: dict) -> tuple[bool, list[str]]:
    low = answer.lower()
    missing = [s for s in q.get("expect_all", []) if s.lower() not in low]
    any_terms = q.get("expect_any", [])
    any_ok = not any_terms or any(t.lower() in low for t in any_terms)
    ok = not missing and any_ok
    if not any_ok:
        missing.append(f"(nessuna di {any_terms})")
    return ok, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", help="id separati da virgola da valutare (debug)")
    ap.add_argument(
        "--provider", help="override provider (default: env RAG_LLM_PROVIDER)"
    )
    ap.add_argument(
        "--model", help="override modello ollama (default: env OLLAMA_MODEL)"
    )
    ap.add_argument(
        "--report-suffix",
        default="",
        help="suffisso del report (es. '_gemma12b' -> rag_generation_report_gemma12b.json)",
    )
    ap.add_argument(
        "--runs",
        type=int,
        default=3,
        help="run per domanda con voto di maggioranza (default 3; 1 = passata singola)",
    )
    args = ap.parse_args()
    if args.runs < 1:
        sys.exit("ERRORE: --runs deve essere >= 1")

    spec = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    top_k = spec.get("top_k", 5)
    only = set(args.only.split(",")) if args.only else None

    from sentence_transformers import SentenceTransformer
    import src.config  # noqa: F401 -- carica .env (RAG_LLM_PROVIDER, OLLAMA_MODEL)
    from src.rag.generator import get_provider
    from src.rag.retriever import Retriever
    from src.rag.store import VectorStore

    store = VectorStore(ROOT / "src" / "data" / "vector_store")
    if not store.is_ready():
        sys.exit("ERRORE: vector store non inizializzato")
    retriever = Retriever(
        store, SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    )
    provider = get_provider(args.provider, ollama_model=args.model)
    print(f"provider: {type(provider).__name__} ({getattr(provider, 'model', 'n/a')})")

    results = []
    hits = 0
    for q in spec["questions"]:
        if only and q["id"] not in only:
            continue
        t0 = time.time()
        chunks = retriever.search(q["query"], top_k=top_k)
        run_results = []
        for _ in range(args.runs):
            answer = provider.generate(q["query"], chunks)
            ok, missing = _check(answer, q)
            run_results.append(
                {"ok": ok, "missing": missing, "answer_head": answer[:200]}
            )
        votes = sum(r["ok"] for r in run_results)
        ok = votes > args.runs / 2  # voto di maggioranza
        hits += ok
        elapsed = time.time() - t0
        results.append(
            {
                "id": q["id"],
                "ok": ok,
                "votes": f"{votes}/{args.runs}",
                "runs": run_results,
                "seconds": round(elapsed, 1),
            }
        )
        mark = "OK " if ok else "MISS"
        print(
            f"[{mark}] {q['id']} voti {votes}/{args.runs} ({elapsed:.0f}s)"
            + ("" if ok else f" manca: {run_results[0]['missing']}")
        )

    total = len(results)
    rate = hits / total if total else 0.0
    print(f"\ngeneration hit rate: {hits}/{total} = {rate:.0%}")

    if args.write:
        report_path = REPORT_PATH.with_name(
            REPORT_PATH.stem + args.report_suffix + REPORT_PATH.suffix
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "provider": type(provider).__name__,
                    "model": getattr(provider, "model", None),
                    "runs_per_question": args.runs,
                    "majority_vote": args.runs > 1,
                    "hits": hits,
                    "total": total,
                    "rate": rate,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
