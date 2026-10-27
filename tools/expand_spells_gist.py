#!/usr/bin/env python3
"""Espande spells.json con le spell della cache gist PathfinderSpellsJSON
assenti dal catalogo (expansion offline, Lotto 1 spell 2026-07-25).

Policy (spec grilling 2026-07-25):
- le entry locali esistenti VINCONO sempre: il gist aggiunge solo le mancanti;
- dedup per nome esatto/normalizzato e forma invertita "X, Greater" (stessa
  logica di enrich_spells._gist_entry);
- nomi con identita' PI (word-boundary su PI_WORDS di legal_filter, es.
  possessivi di divinita') -> pi_local_only/spells_local.json (verbatim);
- prosa con PI -> sanitize word-boundary (sanitize_reference_pi) solo su
  description; gate finale legal_filter = 0;
- provenienza dichiarata in notes + references; manifest aggiornato
  (files.spells + catalogs spells/spells_local).

Default: dry-run (report a video). --write applica e scrive file + report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.enrich_reference import normalize_name
from tools.enrich_spells import CACHE_DIR, load_gist_cache, parse_spell_level
from tools.legal_filter import PI_WORDS
from tools.reference_lib import OGL_DIR, slug, source_id
from tools.sanitize_reference_pi import sanitize_text

ROOT = Path(__file__).resolve().parents[1]
SPELLS_PATH = OGL_DIR / "spells.json"
LOCAL_PATH = ROOT / "data" / "reference" / "pi_local_only" / "spells_local.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"
REPORT_PATH = ROOT / "reports" / "expand_spells_gist.md"

_PI_NAME_RE = re.compile(
    r"\b("
    + "|".join(re.escape(w) for w in sorted(PI_WORDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

_INVERTIBLE_PREFIXES = ("Greater", "Lesser", "Mass")


def is_pi_name(name: str) -> bool:
    """True se il nome contiene un termine PI (word-boundary)."""
    return bool(_PI_NAME_RE.search(name))


def _variants(name: str) -> list[str]:
    """Nome + forma invertita per prefissi Greater/Lesser/Mass."""
    out = [name]
    for prefix in _INVERTIBLE_PREFIXES:
        if name.startswith(prefix + " "):
            out.append(f"{name[len(prefix) + 1:]}, {prefix}")
            break
    return out


def new_gist_records(local_names: list[str], gist_records: list[dict]) -> list[dict]:
    """Record gist il cui nome NON copre nessuna entry locale (esatto,
    normalizzato, invertito in entrambe le direzioni)."""
    local_exact, local_norm = set(), set()
    for n in local_names:
        for v in _variants(n):
            local_exact.add(v)
            local_norm.add(normalize_name(v))
    nuovi = []
    for g in gist_records:
        name = g.get("name", "")
        if not name:
            continue
        cands = set()
        for v in _variants(name):
            cands.add(v)
            cands.add(normalize_name(v))
        if cands & local_exact or cands & local_norm:
            continue
        nuovi.append(g)
    return nuovi


def _tags_for(name: str, mech: dict) -> list[str]:
    tags = ["spell", slug(name).replace("_", "-")]
    if mech.get("school"):
        tags.append(f"school:{mech['school']}")
    levels = mech.get("spell_level") or {}
    if levels:
        tags.append(f"slot:{min(levels.values())}")
        for cls_key in levels:
            for cls in cls_key.split("/"):
                tags.append(f"class:{cls.strip()}")
    return tags


def gist_to_entry(g: dict) -> dict:
    """Record gist -> entry catalogo spells (description sanitizzata)."""
    mech = {}
    for key in (
        "school",
        "casting_time",
        "components",
        "range",
        "duration",
        "saving_throw",
        "targets",
    ):
        value = g.get(key)
        if isinstance(value, str) and value.strip():
            mech[key] = value.strip()
    levels = parse_spell_level(g.get("spell_level") or "")
    if levels:
        mech["spell_level"] = levels
    return {
        "name": g["name"],
        "source": g.get("source") or "Pathfinder SRD",
        "source_id": source_id("pathfinder_srd", g["name"]),
        "prerequisites": [],
        "tags": _tags_for(g["name"], mech),
        "references": [f"PathfinderSpellsJSON gist: {g['name']}"],
        "reference_urls": [
            "https://aonprd.com/SpellDisplay.aspx?ItemName="
            + g["name"].replace(" ", "%20").replace("'", "%27")
        ],
        "description": sanitize_text(g.get("description") or "", description=True),
        "mechanics": mech,
        "notes": (
            "Aggiunta da cache gist PathfinderSpellsJSON (expansion "
            "2026-07-25): assente dal catalogo storico."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--write",
        action="store_true",
        help="scrive spells.json/spells_local.json/manifest + report",
    )
    args = ap.parse_args(argv)

    catalog = json.loads(SPELLS_PATH.read_text(encoding="utf-8"))
    entries = catalog["entries"]
    gist = load_gist_cache(CACHE_DIR)
    if not gist:
        sys.exit("ERRORE: cache gist assente")
    records = list(gist.exact.values())
    nuovi = new_gist_records([e["name"] for e in entries], records)

    local_entries, ogl_entries = [], []
    for g in nuovi:
        entry = gist_to_entry(g)
        (local_entries if is_pi_name(entry["name"]) else ogl_entries).append(entry)

    print(
        f"gist: {len(records)} record; nuovi: {len(nuovi)} "
        f"(OGL {len(ogl_entries)}, PI->local {len(local_entries)})"
    )
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        for e in local_entries[:20]:
            print(f"  PI local: {e['name']}")
        return 0

    entries.extend(ogl_entries)
    catalog["entries"] = entries
    SPELLS_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    local_catalog = {
        "_license": "OGL-1.0a",
        "_source": (
            "PathfinderSpellsJSON gist / Archives of Nethys "
            "(local only, not redistributed)"
        ),
        "entries": local_entries,
    }
    LOCAL_PATH.write_text(
        json.dumps(local_catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    manifest["files"]["spells"]["entries"] = len(entries)
    for c in manifest["catalogs"]:
        if c["kind"] == "spells":
            c["entries"] = len(entries)
            c["last_verified"] = today
    manifest["catalogs"] = [
        c for c in manifest["catalogs"] if c["kind"] != "spells_local"
    ]
    manifest["catalogs"].append(
        {
            "file": "pi_local_only/spells_local.json",
            "kind": "spells_local",
            "source": "PathfinderSpellsJSON gist / Archives of Nethys (aonprd.com)",
            "license": "OGL-1.0a",
            "is_ogc": False,
            "is_pi": False,
            "cup_allowed": False,
            "local_only": True,
            "entries": len(local_entries),
            "notes": (
                "Spell con Product Identity nel nome (possessivi di divinita' "
                "e simili), separate dal catalogo OGL con la policy 2026-07-25 "
                "(reports/expand_spells_gist.md). NON redistribuire. Generato da "
                "tools/expand_spells_gist.py; indicizza con index_rag.py --include-local."
            ),
            "last_verified": today,
        }
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# Expansion spells da cache gist (2026-07-25)",
        "",
        f"- Record gist: {len(records)}",
        f"- Nuove (non in catalogo): {len(nuovi)}",
        f"- Aggiunte a spells.json (OGL): {len(ogl_entries)} (totale {len(entries)})",
        f"- Spostate in spells_local.json (nome PI): {len(local_entries)}",
        "",
        "## Nomi PI spostati in locale",
        "",
    ]
    lines += [f"- {e['name']}" for e in local_entries]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Scritto: {SPELLS_PATH} ({len(entries)} entry)")
    print(f"Scritto: {LOCAL_PATH} ({len(local_entries)} entry, NON committare)")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
