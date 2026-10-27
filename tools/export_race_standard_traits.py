#!/usr/bin/env python3
"""Export dei tratti razziali standard (Taverna curato -> motore).

Slice D6 (2026-08-08) del piano
`sessione-2026-07-16/rapporti/2026-08-02-piano-completamento-db-pcgen-pathbuilder.md`.

Legge il catalogo curato OGL `data/reference/ogl/races.json` ed emette
`taverna-race-standard-traits.json` in
`pathmaster-dd/packages/rules-engine-v2/src/data/`: per OGNI razza, i NOMI
dei suoi tratti standard (mechanics.traits[].name).

Serve alla legality dei tratti ALTERNATIVI Pathbuilder (D1, 702 tratti con
replaces/changes): "un tratto che sostituisce X richiede che la razza abbia
X" si verifica contro questa lista. Razza assente dal curato -> i suoi
replaces sono unknown DICHIARATO dal motore (policy D6), mai indovinati.

Policy OGL/PI: SOLO nomi dei tratti. MAI i testi (description Paizo,
restano nel catalogo Taverna).

Uso:
  python tools/export_race_standard_traits.py                # scrive il JSON
  python tools/export_race_standard_traits.py --report-only  # solo stdout
  --out-dir PATH  (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = REPO_ROOT / "data/reference/ogl/races.json"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)
OUTPUT_FILE = "taverna-race-standard-traits.json"

LICENSE_TEXT = (
    "Nomi e meccaniche: OGL 1.0a (catalogo curato Master-DD-Taverna). "
    "Mai i testi dei tratti (description Paizo): esportati solo i nomi."
)


def extract_traits(catalog: dict) -> dict[str, list[str]]:
    """razza -> nomi dei tratti standard, nell'ordine del catalogo."""
    out: dict[str, list[str]] = {}
    for entry in catalog.get("entries", []):
        mechanics = entry.get("mechanics") or {}
        traits = mechanics.get("traits") or []
        names = [t.get("name") for t in traits if t.get("name")]
        if names:
            out[entry["name"]] = names
    return out


def build_file(catalog: dict, generated_at: str | None = None) -> dict:
    races = extract_traits(catalog)
    all_names = [e.get("name") for e in catalog.get("entries", [])]
    without = sorted(n for n in all_names if n and n not in races)
    return {
        "_provenance": {
            "source": "Master-DD-Taverna data/reference/ogl/races.json "
            "(catalogo curato OGL)",
            "generated_by": "Master-DD-Taverna/tools/export_race_standard_traits.py",
            "license": LICENSE_TEXT,
            "semantics": "Solo i NOMI dei tratti standard per razza. Una razza "
            "assente non ha lista attestata da questa fonte: i "
            "replaces dei suoi tratti alternativi restano unknown "
            "dichiarato (policy D6), mai indovinati.",
        },
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "counts": {
            "races_total": len(all_names),
            "races_with_traits": len(races),
            "without_traits": without,
        },
        "races": races,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    doc = build_file(catalog)
    counts = {k: v for k, v in doc["counts"].items() if k != "without_traits"}
    print(json.dumps(counts, indent=1, ensure_ascii=False))
    print(
        f"senza tratti: {len(doc['counts']['without_traits'])} razze", file=sys.stderr
    )
    if args.report_only:
        return 0
    out_path = args.out_dir / OUTPUT_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"scritto {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
