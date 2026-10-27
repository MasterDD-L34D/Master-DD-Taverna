#!/usr/bin/env python3
"""Sostituisce 'Archives of a deity of magic' -> 'Pathfinder PRD' nei
references di tutti i cataloghi OGL (artifact dell'ordine regole sanitize
pre-2026-07-19: 'Nethys' -> 'a deity of magic' scattava prima della regola
frase 'Archives of Nethys' -> 'Pathfinder PRD'; tool gia' fixato, dati mai
bonificati — appendice di reports/pi_feats_triage.md).

Default: dry-run (conteggi). --write applica.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_lib import OGL_DIR

OLD = "Archives of a deity of magic"
NEW = "Pathfinder PRD"


def fix_entry(entry: dict) -> tuple[dict, int]:
    """Entry con references bonificati + n. sostituzioni."""
    refs = entry.get("references")
    if not isinstance(refs, list):
        return entry, 0
    n = sum(1 for r in refs if isinstance(r, str) and OLD in r)
    if not n:
        return entry, 0
    out = dict(entry)
    out["references"] = [r.replace(OLD, NEW) if isinstance(r, str) else r for r in refs]
    return out, n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    total_subs = 0
    for path in sorted(OGL_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries")
        if not isinstance(entries, list):
            continue
        subs = 0
        new_entries = []
        for e in entries:
            out, n = fix_entry(e)
            new_entries.append(out)
            subs += n
        if not subs:
            continue
        total_subs += subs
        print(f"{path.name}: {subs} references bonificati")
        if args.write:
            data["entries"] = new_entries
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    print(f"totale: {total_subs} sostituzioni")
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
