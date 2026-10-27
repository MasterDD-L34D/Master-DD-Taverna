#!/usr/bin/env python3
"""Arricchisce le description di equipment_mundane.json con il testo flavor
della sezione "Description" delle pagine dettaglio AoN in cache (786/786,
offline; enrichment guidato da eval 2026-07-25).

La description attuale (riga stats) resta in testa; il flavor viene aggiunto
dopo, sanitizzato (description=True). Idempotente: non raddoppia il flavor
se gia' presente. Pagine senza sezione Description: entry invariata (nota
nel report).

Default: dry-run. --write applica. --offline: solo cache (mai rete).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_fetch import cache_path
from tools.reference_lib import OGL_DIR, clean
from tools.sanitize_reference_pi import sanitize_text

EQUIPMENT_PATH = OGL_DIR / "equipment_mundane.json"
REPORT_PATH = (
    Path(__file__).resolve().parents[1] / "reports" / "enrich_equipment_descriptions.md"
)


def parse_equipment_description(html: str) -> str:
    """Sezione <h3 class='framing'>Description</h3> -> testo flavor (fino
    all'h3/h1 successivo o fine contenitore). '' se assente."""
    from bs4 import BeautifulSoup, NavigableString, Tag

    soup = BeautifulSoup(html, "html.parser")
    for h3 in soup.find_all("h3", class_="framing"):
        if clean(h3.get_text()).lower() != "description":
            continue
        parts = []
        node = h3.next_sibling
        while node is not None:
            if isinstance(node, Tag) and node.name in ("h1", "h2", "h3"):
                break
            if isinstance(node, Tag):
                parts.append(node.get_text(" "))
            elif isinstance(node, NavigableString):
                parts.append(str(node))
            node = node.next_sibling
        return clean(" ".join(parts))
    return ""


def enrich_entry(entry: dict, flavor: str) -> dict:
    """Accoda il flavor alla description (dopo \n\n), idempotente."""
    if not flavor:
        return entry
    out = dict(entry)
    current = out.get("description") or ""
    if flavor in current:
        return out
    out["description"] = (current + "\n\n" + flavor) if current else flavor
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--offline", action="store_true", help="solo cache (default)")
    args = ap.parse_args()

    catalog = json.loads(EQUIPMENT_PATH.read_text(encoding="utf-8"))
    enriched = no_section = missing_page = 0
    for entry in catalog["entries"]:
        urls = entry.get("reference_urls") or []
        if not urls or "Display" not in urls[0]:
            missing_page += 1
            continue
        path = cache_path(urls[0])
        if not path.exists():
            missing_page += 1
            continue
        flavor = parse_equipment_description(
            path.read_text(encoding="utf-8", errors="replace")
        )
        if not flavor:
            no_section += 1
            continue
        before = entry.get("description") or ""
        entry.update(enrich_entry(entry, sanitize_text(flavor, description=True)))
        if entry["description"] != before:
            enriched += 1

    print(
        f"entries: {len(catalog['entries'])}; arricchite: {enriched}; "
        f"senza sezione: {no_section}; pagina mancante: {missing_page}"
    )
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        return 0
    EQUIPMENT_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    REPORT_PATH.write_text(
        f"# Enrich equipment descriptions (2026-07-25)\n\n"
        f"- Entries: {len(catalog['entries'])}\n- Arricchite: {enriched}\n"
        f"- Senza sezione Description: {no_section}\n- Pagina mancante: {missing_page}\n",
        encoding="utf-8",
    )
    print(f"Scritto: {EQUIPMENT_PATH}; report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
