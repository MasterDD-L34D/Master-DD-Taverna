#!/usr/bin/env python3
"""Importa da AoN i talenti OGL assenti da feats.json (2026-11-01).

Il censimento AoN vs catalogo del 2026-11-01 ha trovato ~690 talenti OGL
mancanti: feats.json viene dal vecchio bundle GPT arricchito, non da un
import completo dell'indice. Questo tool legge l'indice Feats.aspx, trova i
nomi assenti, scarica le loro pagine FeatDisplay (scrapling, via
reference_fetch, cache su disco) e li AGGIUNGE in coda: le voci esistenti non
si toccano.

Policy: nomi con identita' PI -> pi_local_only/feats_local.json; description
sanitizzata (description=True); gate legal_filter = 0 prima del commit.

Default: dry-run. --write applica. --limit N per un campione.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapling.parser import Selector

from tools.import_archetypes import is_pi_entry
from tools.reference_fetch import fetch
from tools.reference_lib import OGL_DIR, clean, source_id
from tools.restore_feat_prose import parse_feat_page
from tools.sanitize_reference_pi import sanitize_text

FEAT_URL = "https://aonprd.com/FeatDisplay.aspx?ItemName="
INDEX_URL = "https://aonprd.com/Feats.aspx"
ROOT = Path(__file__).resolve().parents[1]
FEATS_PATH = OGL_DIR / "feats.json"
LOCAL_PATH = ROOT / "data" / "reference" / "pi_local_only" / "feats_local.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"


def index_feat_names(html: str) -> list[str]:
    """Nomi dall'indice Feats.aspx (link FeatDisplay, ItemName decodificato),
    in ordine e senza doppioni."""
    return index_names(html, "FeatDisplay.aspx")


def index_names(html: str, display_page: str) -> list[str]:
    """Nomi da un indice AoN: link `<display_page>?ItemName=...` decodificati,
    in ordine e senza doppioni (FeatDisplay.aspx, SpellDisplay.aspx, ...)."""
    out, seen = [], set()
    for a in Selector(html).css(f'a[href*="{display_page}"]'):
        href = a.attrib.get("href", "")
        if "ItemName=" not in href:
            continue
        name = clean(unquote(href.split("ItemName=", 1)[1]))
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


_TYPE_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<types>[^()]+)\)\s*$")


_GRADE_RE = re.compile(r"^(?P<base>.+),\s*(?P<grade>greater|improved|lesser|mythic)$")
_ROMAN = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
}
_ROMAN_END_RE = re.compile(r"^(?P<base>.+)\s(?P<num>ix|iv|v?i{0,3})$")


def norm_name(name: str) -> str:
    """Chiave di confronto: minuscole, apostrofi e spazi uniformi, e
    "X, Greater" letto come "Greater X" (le due forme convivono)."""
    n = re.sub(r"\s+", " ", name.replace("’", "'").replace("`", "'")).strip()
    n = n.lower()
    # Numero romano finale -> arabo: "Summon Nature's Ally III" = "... 3".
    r = _ROMAN_END_RE.match(n)
    if r and r.group("num"):
        n = f"{r.group('base')} {_ROMAN[r.group('num')]}"
    m = _GRADE_RE.match(n)
    return f"{m.group('grade')} {m.group('base')}" if m else n


def missing_feats(index_names: list[str], catalog: list[dict]) -> list[str]:
    """Nomi dell'indice AoN assenti dal catalogo (confronto normalizzato),
    nell'ordine dell'indice e senza doppioni."""
    have = {norm_name(e["name"]) for e in catalog}
    out, seen = [], set()
    for name in index_names:
        key = norm_name(name)
        if key not in have and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def feat_entry(page: dict, url: str) -> dict:
    """Pagina FeatDisplay analizzata (restore_feat_prose.parse_feat_page) ->
    voce di catalogo. Il tipo fra parentesi nel titolo ("(Combat, Teamwork)")
    diventa tag; il nome resta senza parentesi, come nel catalogo esistente."""
    name, tags = page["name"], []
    m = _TYPE_RE.match(page["name"])
    if m:
        name = m.group("name")
        tags = [t.strip().lower() for t in m.group("types").split(",") if t.strip()]
    text = clean(f"{page.get('flavor', '')} Benefit: {page.get('benefit', '')}")
    return {
        "name": name,
        "source": page.get("source", ""),
        "source_id": source_id("feats", name),
        "prerequisites": list(page.get("prerequisites", [])),
        "tags": tags,
        "references": [f"AoN: {name}"],
        "reference_urls": [url],
        "description": sanitize_text(text, description=True),
        "mechanics": {},
    }


def build_new_entries(names, load_page, taken=()):
    """Per ogni nome mancante: pagina analizzata -> voce. `load_page(nome)`
    scarica e analizza (iniettata: i test non vanno in rete). Ritorna
    (ogl, local_pi, falliti); una pagina che fallisce si registra e basta.

    source_id unico (gate test_source_id_unique_globally): `taken` sono gli
    id gia' nel catalogo. Stesso slug da un manuale diverso -> id col manuale
    (due "Inner Light"); stesso slug e stesso manuale -> doppione scartato."""
    ogl, local, failures = [], [], []
    seen = set(taken)
    seen_sources = set()  # (slug base, manuale) gia' importati in questo giro
    for name in names:
        try:
            page = load_page(name)
        except Exception as exc:  # pagina assente, layout inatteso, rete
            failures.append(f"- **{name}**: {exc}")
            continue
        url = FEAT_URL + name.replace(" ", "%20")
        entry = feat_entry(page, url)
        base = entry["source_id"]
        if (base, entry["source"]) in seen_sources:
            continue  # doppione dell'indice (stesso talento, stesso manuale)
        seen_sources.add((base, entry["source"]))
        if base in seen:
            entry["source_id"] = source_id(
                "feats", f"{entry['name']} {entry['source']}"
            )
        seen.add(entry["source_id"])
        # PI nel nome O nella descrizione -> local-only (come gli archetipi).
        (local if is_pi_entry(entry) else ogl).append(entry)
    return ogl, local, failures


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="solo i primi N mancanti")
    args = ap.parse_args(argv)

    catalog = _read(FEATS_PATH)
    local = _read(LOCAL_PATH)["entries"] if LOCAL_PATH.is_file() else []
    index = index_feat_names(fetch(INDEX_URL, delay=2.0))
    missing = missing_feats(index, catalog["entries"] + local)
    if args.limit:
        missing = missing[: args.limit]
    print(
        f"indice AoN: {len(index)}; catalogo: {len(catalog['entries'])}; "
        f"mancanti da importare: {len(missing)}",
        flush=True,
    )

    def load_page(name):
        return parse_feat_page(fetch(FEAT_URL + quote(name), delay=2.0))

    taken = {e["source_id"] for e in catalog["entries"] + local if e.get("source_id")}
    ogl, local_new, failures = build_new_entries(missing, load_page, taken)
    print(
        f"nuovi OGL: {len(ogl)}; PI->local: {len(local_new)}; falliti: {len(failures)}"
    )
    print("\n".join(failures[:30]))
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        for e in ogl[:10]:
            print(f"  + {e['name']} [{', '.join(e['tags'])}] {e['source']}")
        return 0

    catalog["entries"] += ogl
    _write(FEATS_PATH, catalog)
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
    manifest["files"]["feats"]["entries"] = n
    for c in manifest["catalogs"]:
        if c["kind"] == "feats":
            c["entries"] = n
            c["last_verified"] = date.today().isoformat()
        elif c["kind"] == "feats_local":
            c["entries"] = len(local_all)
    _write(MANIFEST_PATH, manifest)
    print(f"scritto: feats.json {n} voci; feats_local {len(local_all)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
