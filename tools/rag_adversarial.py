#!/usr/bin/env python3
"""RAG adversarial QA — sentinelle anti-allucinazione / injection / fonti false (blocco C, 2026-08-01).

12 casi sentinella (data/rag_adversarial_cases.json), 4 famiglie, ispirati alla
suite 05 del ruling-expert-package ma adattati al NOSTRO RAG. Per ogni caso:
retrieval reale (retriever di produzione) -> generazione col provider
configurato (default: RAG_LLM_PROVIDER da .env) -> rubrica DETERMINISTICA
(require_groups / forbid_any, sottostringhe case-insensitive). Nessun LLM-judge.

severity=critico -> il fallimento BLOCCA (mai rilasciare una modifica a
prompt/retrieval/modelli che fallisce una sentinella critica).
severity=regressione -> sentinella positiva di grounding: se fallisce il
retrieval o il prompt si sono degradati; fallisce il runner anche lei.

La suite NON e' conoscenza del modello: non copiarla nei moduli prompt ne'
indicizzarla nel RAG (regola mutuata dalla Guida del ruling-expert-package).

Uso:
    .venv/Scripts/python tools/rag_adversarial.py                 # run, report a video
    .venv/Scripts/python tools/rag_adversarial.py --write         # salva reports/rag_adversarial_baseline.json
    .venv/Scripts/python tools/rag_adversarial.py --compare       # confronta con la baseline salvata
    .venv/Scripts/python tools/rag_adversarial.py --runs 1        # passata singola (default 3, voto di maggioranza)
    .venv/Scripts/python tools/rag_adversarial.py --only inject-reveal-system-prompt

Exit code: 1 se almeno un caso fallisce (o regredisce rispetto alla baseline
con --compare), 0 altrimenti.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES_PATH = ROOT / "data" / "rag_adversarial_cases.json"
BASELINE_PATH = ROOT / "reports" / "rag_adversarial_baseline.json"


def load_cases(path: Path = CASES_PATH) -> tuple[list[dict], int]:
    """Ritorna (casi, top_k di default)."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    return spec["cases"], spec.get("top_k", 5)


def evaluate_answer(case: dict, answer: str) -> dict:
    """Rubrica deterministica: ok, gruppi mancanti, pattern proibiti trovati."""
    low = answer.lower()
    missing = []
    for group in case["rubric"].get("require_groups", []):
        if not any(term.lower() in low for term in group):
            missing.append(group)
    forbidden_hits = [
        p for p in case["rubric"].get("forbid_any", []) if p.lower() in low
    ]
    return {
        "ok": not missing and not forbidden_hits,
        "missing": missing,
        "forbidden_hits": forbidden_hits,
    }


def evaluate_suite(
    cases: list[dict], answer_fn, runs: int = 1, progress=None
) -> list[dict]:
    """Esegue i casi contro `answer_fn(case) -> str` (runs volte, voto di maggioranza).

    Usata sia dal runner live (answer_fn = retrieval+provider) sia dai test CI
    (answer_fn = LLM finto deterministico)."""
    results = []
    for case in cases:
        t0 = time.time()
        run_results = []
        for _ in range(runs):
            answer = answer_fn(case)
            verdict = evaluate_answer(case, answer)
            run_results.append(
                {
                    "ok": verdict["ok"],
                    "missing": verdict["missing"],
                    "forbidden_hits": verdict["forbidden_hits"],
                    "answer": answer,
                }
            )
        votes = sum(r["ok"] for r in run_results)
        ok = votes > runs / 2
        results.append(
            {
                "id": case["id"],
                "family": case["family"],
                "severity": case["severity"],
                "query": case["query"],
                "ok": ok,
                "votes": f"{votes}/{runs}",
                "runs": run_results,
                "seconds": round(time.time() - t0, 1),
            }
        )
        if progress:
            progress(results[-1])
    return results


def summarize(results: list[dict]) -> dict:
    crit_fail = [r["id"] for r in results if not r["ok"] and r["severity"] == "critico"]
    regr_fail = [r["id"] for r in results if not r["ok"] and r["severity"] != "critico"]
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "critical_failures": crit_fail,
        "regression_failures": regr_fail,
        "ok": not crit_fail and not regr_fail,
    }


def _print_result(r: dict) -> None:
    mark = "OK  " if r["ok"] else ("CRIT" if r["severity"] == "critico" else "MISS")
    line = f"[{mark}] {r['id']} ({r['family']}) voti {r['votes']} ({r['seconds']:.0f}s)"
    if not r["ok"]:
        first = r["runs"][0]
        detail = []
        if first["missing"]:
            detail.append(
                "manca: " + " / ".join("|".join(g[:3]) for g in first["missing"])
            )
        if first["forbidden_hits"]:
            detail.append("proibito: " + ", ".join(first["forbidden_hits"]))
        line += " -- " + "; ".join(detail)
    print(line)


def _live_answer_fn(retriever, provider, top_k: int):
    def answer(case: dict) -> str:
        chunks = retriever.search(case["query"], top_k=top_k)
        return provider.generate(case["query"], chunks)

    return answer


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="salva reports/rag_adversarial_baseline.json",
    )
    ap.add_argument(
        "--compare",
        action="store_true",
        help="confronta con la baseline salvata (regressione = caso che passava e ora fallisce)",
    )
    ap.add_argument("--only", help="id separati da virgola da valutare (debug)")
    ap.add_argument(
        "--provider", help="override provider (default: env RAG_LLM_PROVIDER)"
    )
    ap.add_argument(
        "--model", help="override modello ollama (default: env OLLAMA_MODEL)"
    )
    ap.add_argument(
        "--runs",
        type=int,
        default=3,
        help="run per caso con voto di maggioranza (default 3; 1 = passata singola)",
    )
    args = ap.parse_args()
    if args.runs < 1:
        sys.exit("ERRORE: --runs deve essere >= 1")

    cases, top_k = load_cases()
    only = set(args.only.split(",")) if args.only else None
    if only:
        cases = [c for c in cases if c["id"] in only]

    from sentence_transformers import SentenceTransformer
    import src.config  # noqa: F401 -- carica .env (RAG_LLM_PROVIDER, OLLAMA_MODEL)
    from src.rag.generator import get_provider
    from src.rag.retriever import Retriever
    from src.rag.store import VectorStore

    store = VectorStore(ROOT / "src" / "data" / "vector_store")
    if not store.is_ready():
        sys.exit(
            "ERRORE: vector store non inizializzato; esegui tools/index_rag.py --include-local"
        )
    retriever = Retriever(
        store, SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    )
    provider = get_provider(args.provider, ollama_model=args.model)
    model = getattr(provider, "model", None)
    print(
        f"provider: {type(provider).__name__} ({model or 'n/a'}), casi: {len(cases)}, run/caso: {args.runs}"
    )

    results = evaluate_suite(
        cases,
        _live_answer_fn(retriever, provider, top_k),
        runs=args.runs,
        progress=_print_result,
    )
    summary = summarize(results)
    print(
        f"\npassate: {summary['passed']}/{summary['total']}"
        f" | critici falliti: {summary['critical_failures'] or 'nessuno'}"
        f" | grounding fallito: {summary['regression_failures'] or 'nessuno'}"
    )

    if args.write:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "provider": type(provider).__name__,
                    "model": model,
                    "runs_per_case": args.runs,
                    "top_k": top_k,
                    "cases_path": str(CASES_PATH.relative_to(ROOT)),
                    "note": "Baseline sentinelle avversariali RAG. Riesegui tools/rag_adversarial.py --compare dopo OGNI modifica a prompt/retrieval/modelli. Fallimento critico = blocco. La suite NON e' conoscenza del modello.",
                    "summary": summary,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Baseline: {BASELINE_PATH}")

    if args.compare:
        if not BASELINE_PATH.exists():
            sys.exit(
                f"ERRORE: baseline non trovata ({BASELINE_PATH}); generala con --write"
            )
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        base_ok = {r["id"]: r["ok"] for r in baseline["results"]}
        # Regressione = caso VERDE in baseline che ora fallisce (incluso un
        # NUOVO fallimento critico): e' questo che blocca. Un caso gia' rosso
        # in baseline e' una debolezza nota tracciata, non un blocco.
        regressions = [r["id"] for r in results if base_ok.get(r["id"]) and not r["ok"]]
        fixed = [r["id"] for r in results if r["ok"] and base_ok.get(r["id"]) is False]
        print(
            f"confronto con baseline {baseline.get('generated_at', '?')}"
            f" ({baseline.get('provider')}/{baseline.get('model')}):"
            f" regressioni: {regressions or 'nessuna'}; risolti: {fixed or 'nessuno'}"
        )
        return 1 if regressions else 0

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
