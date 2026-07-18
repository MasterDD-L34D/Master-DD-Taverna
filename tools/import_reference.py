#!/usr/bin/env python3
"""Import reference data OGC da aonprd.com (1e) in cataloghi OGL strutturati.

Ogni dominio ha un parser parse_<domain>(html) -> list[dict] (entry nel
formato catalogo) e un builder build_<domain>() che scarica le pagine via
tools.reference_fetch e scrive/aggiorna il catalogo JSON.

Uso:
  python tools/import_reference.py --domain abilities
  python tools/import_reference.py --domain races --write
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from tools.reference_fetch import fetch

OGL_DIR = Path(__file__).resolve().parents[1] / "data/reference/ogl"
LICENSE = "Open Game Content under OGL 1.0a. See LICENSE-OGL.txt and COPYRIGHT_NOTICE.txt."
SOURCE = "Pathfinder RPG Reference Document © 2011 Paizo Publishing, LLC; Archives of Nethys (aonprd.com)."

BASE = "https://aonprd.com/"


def slug(name):
    """Nome -> slug snake_case per source_id."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def source_id(source_slug, name):
    """Pattern catalogo: <slug_sorgente>:<slug_nome>."""
    return f"{source_slug}:{slug(name)}"


def clean(text):
    """Normalizza whitespace."""
    return " ".join(text.split())


def table_rows(table):
    """<table> -> lista di dict {header: cella} (header dal primo <tr>)."""
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [clean(c.get_text()) for c in rows[0].find_all(["th", "td"])]
    out = []
    for row in rows[1:]:
        cells = [clean(c.get_text()) for c in row.find_all(["th", "td"])]
        if len(cells) == len(headers) and any(cells):
            out.append(dict(zip(headers, cells)))
    return out


def write_catalog(path, entries, license_text=LICENSE, source_text=SOURCE):
    """Scrive il catalogo con header _license/_source (default: costanti AoN;
    i builder di merge passano gli header originali del catalogo esistente)."""
    payload = {"_license": license_text, "_source": source_text, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"scritto {path} ({len(entries)} entry)")


def parse_abilities(html):
    """Pagina 'Generating Ability Scores': tabella costi + budget campagna."""
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        headers = [clean(c.get_text()) for c in trs[0].find_all(["th", "td"])] if trs else []
        if "Score" in headers and "Points" in headers:
            for row in table_rows(table):
                if row.get("Score", "").isdigit():
                    name = f"Score {row['Score']}"
                    entries.append({
                        "name": name,
                        "source": "PFRPG Core",
                        "source_id": source_id("pfrpg_core", name),
                        "prerequisites": [],
                        "tags": ["ability", "point-buy"],
                        "references": ["AoN: Generating Ability Scores"],
                        "reference_urls": [BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"],
                        "description": f"Point-buy: il punteggio di caratteristica {row['Score']} costa {row['Points']} punti.",
                        "mechanics": {"kind": "ability_cost", "score": int(row["Score"]), "cost": int(row["Points"])},
                    })
        elif "Campaign Type" in headers:
            for row in table_rows(table):
                name = row.get("Campaign Type", "")
                if name and row.get("Points", "").lstrip("-").isdigit():
                    entries.append({
                        "name": name,
                        "source": "PFRPG Core",
                        "source_id": source_id("pfrpg_core", name),
                        "prerequisites": [],
                        "tags": ["ability", "point-buy", "campaign"],
                        "references": ["AoN: Generating Ability Scores"],
                        "reference_urls": [BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"],
                        "description": f"Point-buy: la campagna {name} assegna {row['Points']} punti.",
                        "mechanics": {"kind": "campaign_budget", "points": int(row["Points"])},
                    })
    return entries


def build_abilities(write=False):
    url = BASE + "Rules.aspx?Name=Generating%20Ability%20Scores&Category=Getting%20Started"
    entries = parse_abilities(fetch(url))
    assert len(entries) >= 16, f"abilities: attese >=16 entry, trovate {len(entries)}"
    if write:
        write_catalog(OGL_DIR / "abilities.json", entries)
    else:
        print(f"report: {len(entries)} entry (write=False, nessuna scrittura)")


DOMAINS = {"abilities": build_abilities}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", required=True, choices=sorted(DOMAINS))
    ap.add_argument("--write", action="store_true", help="scrivi il catalogo (default: solo report)")
    args = ap.parse_args(argv)
    print(f"domain: {args.domain} (write={args.write})")
    DOMAINS[args.domain](write=args.write)


if __name__ == "__main__":
    main()
