#!/usr/bin/env python3
"""Importa da AoN gli incantesimi OGL assenti da spells.json (2026-11-01).

import_spells.py arricchisce le voci esistenti ma non ne aggiunge; il
censimento AoN vs catalogo del 2026-11-01 ha trovato ~200 incantesimi OGL
mancanti. Questo tool legge l'indice Spells.aspx?Class=All, trova i nomi
assenti, scarica le pagine SpellDisplay (scrapling via reference_fetch,
cache su disco) e li AGGIUNGE in coda, senza toccare le voci esistenti.
Meccaniche da import_spells.parse_spell; descrizione dalla sezione
Description del solo blocco richiesto.

Default: dry-run. --write applica. --limit N per un campione.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup, Tag

from tools.import_archetypes import is_pi_entry
from tools.import_feats_aon import _read, _write, index_names, missing_feats
from tools.import_spells import _find_spell_block, parse_spell
from tools.reference_fetch import fetch
from tools.reference_lib import OGL_DIR, clean, source_id
from tools.sanitize_reference_pi import sanitize_text

INDEX_URL = "https://aonprd.com/Spells.aspx?Class=All"
SPELL_URL = "https://aonprd.com/SpellDisplay.aspx?ItemName="
ROOT = Path(__file__).resolve().parents[1]
SPELLS_PATH = OGL_DIR / "spells.json"
LOCAL_PATH = ROOT / "data" / "reference" / "pi_local_only" / "spells_local.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"


def missing_spells(index_html: str, catalog: list[dict]) -> list[str]:
    """Nomi dell'indice Spells.aspx assenti dal catalogo (stesso confronto
    normalizzato dei talenti, numeri romani compresi)."""
    return missing_feats(index_names(index_html, "SpellDisplay.aspx"), catalog)


def spell_entry(parsed: dict, description: str) -> dict:
    """Voce di catalogo da parse_spell + descrizione. Tag nel formato delle
    voci esistenti: school:, slot: (livello piu' basso), descrittori, class:."""
    mech = parsed["mechanics"]
    levels = mech.get("spell_level", {})
    tags = [f"school:{mech['school']}"] if mech.get("school") else []
    if levels:
        tags.append(f"slot:{min(levels.values())}")
    tags += list(mech.get("descriptors", []))
    tags += [f"class:{c}" for c in levels]
    return {
        "name": parsed["name"],
        "source": parsed["source"],
        "source_id": source_id("spells", parsed["name"]),
        "prerequisites": [],
        "tags": tags,
        "references": parsed["references"],
        "reference_urls": parsed["reference_urls"],
        "description": sanitize_text(description, description=True),
        "mechanics": mech,
    }


def spell_description(html: str, name: str) -> str:
    """Testo della sezione Description del blocco `name` (fino al blocco
    successivo, varianti e mythic esclusi). Stringa vuota se assente."""
    h1 = _find_spell_block(BeautifulSoup(html, "html.parser"), name)
    if h1 is None:
        return ""
    parts, inside = [], False
    for node in h1.next_siblings:
        if isinstance(node, Tag):
            classes = node.get("class") or []
            if node.name in ("h1", "h2") and "title" in classes:
                break
            if node.name == "h3":
                inside = clean(node.get_text()).lower() == "description"
                continue
            if node.name == "br":
                if inside:
                    parts.append(" ")
                continue
        if inside:
            parts.append(node.get_text() if isinstance(node, Tag) else str(node))
    return clean("".join(parts))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="solo i primi N mancanti")
    args = ap.parse_args(argv)

    catalog = _read(SPELLS_PATH)
    local = _read(LOCAL_PATH)["entries"] if LOCAL_PATH.is_file() else []
    missing = missing_spells(fetch(INDEX_URL, delay=2.0), catalog["entries"] + local)
    if args.limit:
        missing = missing[: args.limit]
    print(
        f"catalogo: {len(catalog['entries'])}; mancanti da importare: {len(missing)}",
        flush=True,
    )

    ogl, local_new, failures = [], [], []
    for name in missing:
        try:
            html = fetch(SPELL_URL + quote(name), delay=2.0)
            parsed = parse_spell(html, name)
            if parsed is None:
                raise ValueError("blocco non trovato nella pagina")
        except Exception as exc:  # pagina assente, layout inatteso, rete
            failures.append(f"- **{name}**: {exc}")
            continue
        entry = spell_entry(parsed, spell_description(html, name))
        # PI nel nome O nella descrizione -> local-only (come gli archetipi).
        (local_new if is_pi_entry(entry) else ogl).append(entry)
    print(
        f"nuovi OGL: {len(ogl)}; PI->local: {len(local_new)}; falliti: {len(failures)}"
    )
    print("\n".join(failures[:30]))
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        for e in ogl[:10]:
            print(f"  + {e['name']} [{', '.join(e['tags'][:3])}] {e['source']}")
        return 0

    catalog["entries"] += ogl
    _write(SPELLS_PATH, catalog)
    local_all = local + local_new
    _write(
        LOCAL_PATH,
        {
            "_license": "OGL-1.0a",
            "_source": "Archives of Nethys (local only, not redistributed)",
            "entries": local_all,
        },
    )
    manifest = _read(MANIFEST_PATH)
    n = len(catalog["entries"])
    manifest["files"]["spells"]["entries"] = n
    for c in manifest["catalogs"]:
        if c["kind"] == "spells":
            c["entries"] = n
            c["last_verified"] = date.today().isoformat()
        elif c["kind"] == "spells_local":
            c["entries"] = len(local_all)
    _write(MANIFEST_PATH, manifest)
    print(f"scritto: spells.json {n} voci; spells_local {len(local_all)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
