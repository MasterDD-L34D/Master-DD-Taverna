#!/usr/bin/env python3
"""Export dei requisiti razziali degli archetipi (Taverna curato -> motore).

Slice D6 (2026-08-08) del piano
`sessione-2026-07-16/rapporti/2026-08-02-piano-completamento-db-pcgen-pathbuilder.md`.

Legge il catalogo curato OGL `data/reference/ogl/archetypes.json` (949 entry,
fonte AoN) ed emette `taverna-archetype-race-reqs.json` in
`pathmaster-dd/packages/rules-engine-v2/src/data/`: per OGNI archetipo con
`mechanics.race_req[]` non vuoto — {class, name, race_req, source_id}.

E' la fonte della legality razziale archetipi del builder (D6): il match
Taverna <-> Pathbuilder avviene nel motore per nome normalizzato ESPLICITO
(normalizePbName), mai euristico. Gli archetipi senza race_req NON entrano
nel file: "nessun requisito attestato dalla fonte curata" e' un DATO che il
motore dichiara (policy in INTERPRETATIONS.md), non un buco nascosto.

Policy OGL/PI: SOLO nomi + meccaniche strutturate. MAI description.

Uso:
  python tools/export_archetype_race_reqs.py                # scrive il JSON
  python tools/export_archetype_race_reqs.py --report-only  # solo stdout
  --out-dir PATH  (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = REPO_ROOT / "data/reference/ogl/archetypes.json"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)
OUTPUT_FILE = "taverna-archetype-race-reqs.json"

LICENSE_TEXT = (
    "Nomi e meccaniche: OGL 1.0a (catalogo curato Master-DD-Taverna, fonte "
    "Archives of Nethys). Nessun testo di regole esportato (mai description)."
)


def extract_race_reqs(catalog: dict) -> list[dict]:
    """Le entry con mechanics.race_req non vuoto, in forma minima dichiarata."""
    out: list[dict] = []
    for entry in catalog.get("entries", []):
        mechanics = entry.get("mechanics") or {}
        race_req = mechanics.get("race_req") or []
        if not race_req:
            continue
        out.append(
            {
                "class": mechanics.get("class"),
                "name": entry.get("name"),
                "race_req": list(race_req),
                "source_id": entry.get("source_id"),
            }
        )
    return out


def build_file(catalog: dict, generated_at: str | None = None) -> dict:
    rows = extract_race_reqs(catalog)
    classes: dict[str, int] = {}
    for r in rows:
        classes[r["class"]] = classes.get(r["class"], 0) + 1
    return {
        "_provenance": {
            "source": "Master-DD-Taverna data/reference/ogl/archetypes.json "
            "(catalogo curato OGL, fonte AoN)",
            "generated_by": "Master-DD-Taverna/tools/export_archetype_race_reqs.py",
            "license": LICENSE_TEXT,
            "semantics": "Solo gli archetipi con race_req attestato. Chi non c'e': "
            "nessun requisito razziale NOTO da questa fonte (assenza "
            "di dato, non prova di assenza — policy D6 nel motore).",
        },
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "counts": {
            "entries_total": len(catalog.get("entries", [])),
            "with_race_req": len(rows),
            "classes": dict(sorted(classes.items())),
        },
        "race_reqs": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    doc = build_file(catalog)
    print(json.dumps(doc["counts"], indent=1, ensure_ascii=False))
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
