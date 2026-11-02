#!/usr/bin/env python3
"""Importa da AoN gli oggetti magici assenti da items.json (2026-11-02).

Il censimento AoN vs catalogo del 2026-11-01 ha trovato items.json all'1%
(257 voci contro ~3800 famiglie). Una voce per FAMIGLIA: la pagina di
dettaglio AoN (Magic*Display.aspx?FinalName=...) e' una per famiglia e
contiene tutte le varianti (+1..+5) con i loro prezzi. Fetch con scrapling
via reference_fetch (cache su disco); le voci esistenti non si toccano.

Default: dry-run. --write applica. --limit N per un campione.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup, Tag
from scrapling.parser import Selector

from tools.import_archetypes import is_pi_entry
from tools.import_feats_aon import _read, _write, norm_name
from tools.reference_fetch import fetch
from tools.reference_lib import OGL_DIR, clean, source_id
from tools.sanitize_reference_pi import sanitize_text

BASE = "https://aonprd.com/"
ROOT = Path(__file__).resolve().parents[1]
ITEMS_PATH = OGL_DIR / "items.json"
LOCAL_PATH = ROOT / "data" / "reference" / "pi_local_only" / "items_local.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"

_WONDROUS_SLOTS = ["Belts", "Body", "Chest", "Eyes", "Feet", "Hands", "Head",
                   "Headband", "Neck", "Shoulders", "Wrist", "Other", "Ioun"]
# (indice, pagina di dettaglio, categoria). Stessi indici del censimento AoN
# del 2026-11-01; un indice che non risponde si registra e si salta.
INDEXES = (
    [(f"{BASE}MagicWondrous.aspx?FinalSlot={s}", "MagicWondrousDisplay.aspx", "wondrous")
     for s in _WONDROUS_SLOTS]
    + [
        (f"{BASE}MagicRings.aspx", "MagicRingsDisplay.aspx", "ring"),
        (f"{BASE}MagicRods.aspx?Category=Metamagic", "MagicRodsDisplay.aspx", "rod"),
        (f"{BASE}MagicRods.aspx?Category=Other", "MagicRodsDisplay.aspx", "rod"),
        (f"{BASE}MagicStaves.aspx", "MagicStavesDisplay.aspx", "staff"),
        (f"{BASE}MagicWeapons.aspx?Category=SpecificWeapon", "MagicWeaponsDisplay.aspx", "weapon"),
        (f"{BASE}MagicWeapons.aspx?Category=MeleeWeaponQuality", "MagicWeaponsDisplay.aspx", "weapon quality"),
        (f"{BASE}MagicWeapons.aspx?Category=RangedWeaponQuality", "MagicWeaponsDisplay.aspx", "weapon quality"),
        (f"{BASE}MagicArmor.aspx?Category=SpecificArmor", "MagicArmorDisplay.aspx", "armor"),
        (f"{BASE}MagicArmor.aspx?Category=SpecificShield", "MagicArmorDisplay.aspx", "shield"),
        (f"{BASE}MagicArmor.aspx?Category=ArmorQuality", "MagicArmorDisplay.aspx", "armor quality"),
        (f"{BASE}MagicArmor.aspx?Category=ShieldQuality", "MagicArmorDisplay.aspx", "shield quality"),
        (f"{BASE}MagicCursed.aspx", "MagicCursedDisplay.aspx", "cursed"),
        (f"{BASE}MagicIntelligent.aspx", "MagicIntelligentDisplay.aspx", "intelligent"),
        (f"{BASE}MagicArtifacts.aspx?MinorMajor=Minor", "MagicArtifactsDisplay.aspx", "artifact"),
        (f"{BASE}MagicArtifacts.aspx?MinorMajor=Major", "MagicArtifactsDisplay.aspx", "artifact"),
        (f"{BASE}MagicPotions.aspx", "MagicPotionsDisplay.aspx", "potion"),
    ]
)

_BOOK_RE = re.compile(r"\s*(?P<book>[^,]+?)\s+pg\.?\s*\d+")


def _value(parts: list[str]) -> str:
    """Testo di un campo: spazi uniformi, niente "( " lasciato da un'immagine
    rimossa, niente separatore finale."""
    text = clean("".join(parts)).replace("( ", "(")
    return text.strip().rstrip(";,").strip()


def parse_item_page(html: str) -> dict:
    """Pagina Magic*Display AoN -> campi grezzi della famiglia.

    Etichette in <b> (Source, Aura, CL, Slot, Price, Weight; nella sezione
    Construction Requirements e Cost), sezioni aperte da h3.framing; il blocco
    finisce al prossimo h1/h2.title. Fonte: il Core Rulebook se citato
    (le altre sono ristampe, IMPORT_PLAYBOOK), altrimenti il primo libro."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="MainContent_DataListTypes")
    h1 = table.find("h1", class_="title") if table else None
    if h1 is None:
        raise ValueError("h1.title non trovato (pagina non Magic*Display?)")
    fields: dict[str, list[str]] = {}
    description: list[str] = []
    label, section = None, "header"
    for node in h1.next_siblings:
        if isinstance(node, Tag):
            if node.name in ("h1", "h2") and "title" in (node.get("class") or []):
                break
            if node.name == "h3":
                section, label = clean(node.get_text()).lower(), None
                continue
            if node.name == "b" and section != "description":
                label = clean(node.get_text())
                # Armi specifiche: in Construction il costo si chiama "Price".
                if section == "construction" and label == "Price":
                    label = "Cost"
                fields.setdefault(label, [])
                continue
            if node.name == "br":
                if section == "description":
                    description.append(" ")
                else:
                    label = None
                continue
        text = node.get_text() if isinstance(node, Tag) else str(node)
        if section == "description":
            description.append(text)
        elif label is not None:
            fields[label].append(text)
    get = {k: _value(v) for k, v in fields.items()}
    books = [m.group("book").strip() for m in _BOOK_RE.finditer(get.get("Source", ""))]
    core = [b for b in books if "Core Rulebook" in b]
    reqs = [r.strip() for r in get.get("Requirements", "").split(",") if r.strip()]
    return {
        "name": clean(h1.get_text()),
        "source": (core or books or [""])[0],
        "aura": get.get("Aura", ""),
        "cl": get.get("CL", ""),
        "slot": get.get("Slot", ""),
        "price": get.get("Price", ""),
        "weight": get.get("Weight", ""),
        "description": clean("".join(description)),
        "requirements": reqs,
        "cost": get.get("Cost", ""),
    }

# "Cloak of Resistance (+1)" -> famiglia + variante fra parentesi finali.
_VARIANT_RE = re.compile(r"^(?P<family>.+?)\s*\((?P<variant>[^()]+)\)\s*$")


def index_families(html: str, display_page: str) -> list[dict]:
    """Famiglie da un indice AoN degli oggetti: link `<display_page>?FinalName=`
    raggruppati per famiglia (testo del link senza la variante fra parentesi).
    Per famiglia: il primo FinalName (basta una pagina) e le varianti viste."""
    out: dict[str, dict] = {}
    for a in Selector(html).css(f'a[href*="{display_page}"]'):
        href = a.attrib.get("href", "")
        # Wondrous/anelli/verghe usano FinalName=, staves/armi/armature/
        # qualita'/artefatti ItemName= (indici reali, 2026-11-02).
        param = next((p for p in ("FinalName", "ItemName") if f"{p}=" in href), None)
        if param is None:
            continue
        final = clean(unquote(href.split(f"{param}=", 1)[1]))
        text = clean(" ".join(a.css("::text").getall()))
        m = _VARIANT_RE.match(text)
        family, variant = (m.group("family"), m.group("variant")) if m else (text, None)
        fam = out.setdefault(
            family, {"family": family, "final_name": final, "param": param, "variants": []}
        )
        if variant and variant not in fam["variants"]:
            fam["variants"].append(variant)
    return list(out.values())


_ITEM_SUFFIX_RE = re.compile(r"\s*(\([^()]*\)|[+-]\d+)\s*$")


def _family_key(name: str) -> str:
    """Chiave di famiglia: via il bonus finale (+1) e la variante finale fra
    parentesi ((Type I)), poi la normalizzazione comune di talenti/incantesimi."""
    prev = None
    while prev != name:
        prev, name = name, _ITEM_SUFFIX_RE.sub("", name)
    return norm_name(name)


def missing_families(families: list[dict], catalog: list[dict]) -> list[dict]:
    """Famiglie dell'indice AoN assenti dal catalogo (voci esistenti per
    variante: "Cloak of Resistance +1" copre la famiglia Cloak of Resistance)."""
    have = {_family_key(e["name"]) for e in catalog}
    return [f for f in families if _family_key(f["family"]) not in have]


def item_entry(page: dict, category: str, url: str, variants: list[str]) -> dict:
    """Pagina analizzata -> voce di catalogo, nella forma delle voci esistenti
    (tag categoria + slot:, requisiti di costruzione come prerequisites) piu'
    i campi strutturati in mechanics, varianti comprese."""
    tags = [category] + ([f"slot:{page['slot']}"] if page.get("slot") else [])
    return {
        "name": page["name"],
        "source": page["source"],
        "source_id": source_id("items", page["name"]),
        "prerequisites": list(page["requirements"]),
        "tags": tags,
        "references": [f"AoN: {page['name']}"],
        "reference_urls": [url],
        "description": sanitize_text(page["description"], description=True),
        "mechanics": {
            "category": category,
            "aura": page["aura"],
            "cl": page["cl"],
            "slot": page["slot"],
            "price": page["price"],
            "weight": page["weight"],
            "cost": page["cost"],
            "variants": list(variants),
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="solo le prime N famiglie mancanti")
    args = ap.parse_args(argv)

    catalog = _read(ITEMS_PATH)
    local = _read(LOCAL_PATH)["entries"] if LOCAL_PATH.is_file() else []

    # Famiglie da tutti gli indici, una volta sola (la prima categoria vince).
    todo, seen_fam, failures = [], set(), []
    for url, display, category in INDEXES:
        try:
            fams = index_families(fetch(url, delay=2.0), display)
        except Exception as exc:  # indice assente o rete
            failures.append(f"- indice {url}: {exc}")
            continue
        for fam in fams:
            key = _family_key(fam["family"])
            if key not in seen_fam:
                seen_fam.add(key)
                todo.append((fam, display, category))
    missing = {id(f) for f in missing_families([t[0] for t in todo], catalog["entries"] + local)}
    todo = [t for t in todo if id(t[0]) in missing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"famiglie AoN: {len(seen_fam)}; mancanti da importare: {len(todo)}", flush=True)

    ogl, local_new = [], []
    taken = {e["source_id"] for e in catalog["entries"] + local if e.get("source_id")}
    for fam, display, category in todo:
        url = f"{BASE}{display}?{fam['param']}={quote(fam['final_name'])}"
        try:
            page = parse_item_page(fetch(url, delay=2.0))
        except Exception as exc:  # pagina assente o layout inatteso
            failures.append(f"- **{fam['family']}**: {exc}")
            continue
        entry = item_entry(page, category, url, fam["variants"])
        if entry["source_id"] in taken:  # stesso nome da un altro manuale
            entry["source_id"] = source_id("items", f"{entry['name']} {entry['source']}")
            if entry["source_id"] in taken:
                continue
        taken.add(entry["source_id"])
        (local_new if is_pi_entry(entry) else ogl).append(entry)
    print(f"nuovi OGL: {len(ogl)}; PI->local: {len(local_new)}; falliti: {len(failures)}")
    print("\n".join(failures[:40]))
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        for e in ogl[:12]:
            m = e["mechanics"]
            print(f"  + {e['name']} [{m['category']}; {m['slot']}; {m['price'][:30]}] {e['source']}")
        return 0

    catalog["entries"] += ogl
    _write(ITEMS_PATH, catalog)
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
    manifest["files"]["items"]["entries"] = n
    for c in manifest["catalogs"]:
        if c["kind"] == "items":
            c["entries"] = n
            c["last_verified"] = date.today().isoformat()
    _write(MANIFEST_PATH, manifest)
    print(f"scritto: items.json {n} voci; items_local {len(local_all)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
