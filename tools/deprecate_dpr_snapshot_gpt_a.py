#!/usr/bin/env python3
"""Marca DEPRECATO il `benchmark.dpr_snapshot` GPT-A nel corpus build (G2, REF-06).

Contesto: il DPR dichiarato dal GPT-A (MinMax Builder) non e' verificato:
la riconciliazione 2026-07-25 (pathmaster-dd, report
`docs/superpowers/research/2026-07-25-dpr-reconciliation.md`) ha misurato
sovrastime fino al 99% a L5+. G2 depreca lo snapshot:

- a LIVELLO 1 la fonte del DPR diventa il motore (`computeDpr`, ENG-18);
- a L5+ lo snapshot RESTA nel dato (deprecazione, non rimozione) marcato
  `benchmark.dpr_snapshot_deprecation.stato = "deprecated"` e va presentato
  con badge "stima GPT-A non verificata" fino a Leva 2 / class features.

Il tool e' idempotente e NON tocca `archive/` (backup congelato pre-rebuild).
Uso: `python tools/deprecate_dpr_snapshot_gpt_a.py [--check]`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

MARKER: dict[str, Any] = {
    "stato": "deprecated",
    "task": "G2 (REF-06)",
    "data": "2026-07-28",
    "tool": "tools/deprecate_dpr_snapshot_gpt_a.py",
    "motivo": (
        "DPR GPT-A/MinMax non verificato: a L5+ sovrastima il motore "
        "deterministico (delta fino al 99%, report dpr-reconciliation)."
    ),
    "sostituto_l1": (
        "computeDpr (ENG-18) del motore pathmaster-dd: fonte delegata per il "
        "DPR di livello 1 (delta medio -0.9% alla riconciliazione 2026-07-25)."
    ),
    "badge_l5plus": (
        "stima GPT-A non verificata — fino a chiusura Leva 2 / class "
        "features del motore"
    ),
    "rimozione_prevista": (
        "dopo Leva 2 (motore copre L5+): deprecazione completa MinMax e "
        "rimozione dello snapshot"
    ),
}


def iter_build_files() -> Iterable[Path]:
    """Corpus vivo: top level + strict/ (archive/ e' backup congelato)."""
    top = Path("src/data/builds")
    for path in sorted(top.glob("*.json")):
        if not path.name.startswith("_"):
            yield path
    strict = top / "strict"
    if strict.exists():
        for path in sorted(strict.rglob("*.json")):
            yield path


def _mark_benchmark(node: Any) -> bool:
    """Marca un dict benchmark se ha dpr_snapshot e non e' gia' marcato."""
    if not isinstance(node, dict) or "dpr_snapshot" not in node:
        return False
    if node.get("dpr_snapshot_deprecation") == MARKER:
        return False
    node["dpr_snapshot_deprecation"] = dict(MARKER)
    return True


def process_file(path: Path, check: bool) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return "skip"

    has_snapshot = (
        isinstance(payload.get("benchmark"), dict)
        and "dpr_snapshot" in payload["benchmark"]
    )
    touched = _mark_benchmark(payload.get("benchmark"))
    composite = payload.get("composite")
    if isinstance(composite, dict):
        build = composite.get("build")
        if isinstance(build, dict):
            bench = build.get("benchmark")
            has_snapshot = has_snapshot or (
                isinstance(bench, dict) and "dpr_snapshot" in bench
            )
            touched = _mark_benchmark(bench) or touched

    if not has_snapshot:
        return "skip"
    if check:
        return "would-mark" if touched else "ok"
    if touched:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return "marked"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="non scrive: elenca i file che verrebbero marcati",
    )
    args = parser.parse_args()

    counts: dict[str, int] = {"marked": 0, "would-mark": 0, "ok": 0, "skip": 0}
    for path in iter_build_files():
        outcome = process_file(path, args.check)
        counts[outcome] += 1
        if outcome not in ("skip", "ok"):
            print(f"[{outcome}] {path}")

    print(
        f"\nTotale: {counts['marked']} marcati, {counts['would-mark']} da marcare, "
        f"{counts['ok']} gia' marcati, {counts['skip']} senza dpr_snapshot."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
