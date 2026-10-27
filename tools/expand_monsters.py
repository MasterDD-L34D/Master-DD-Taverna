#!/usr/bin/env python3
"""Espansione dataset mostri oltre i 199 (lotto 2026-07-25).

Fonte: indici AoN Monsters/MythicMonsters/NPCs (link MonsterDisplay/NPCDisplay)
+ parser di PathfinderMonsterDatabase (parsePage, riusato come libreria dal
clone in sessione-2026-07-16/ricerca/). Destinazione: pi_local_only
(monsters_local.json + npcs_local.json), NON committati.

Modalita':
  --fetch    scarica tutte le pagine degli indici via reference_fetch (2s,
             cache: resume gratuito se interrotto). Default: solo le mancanti.
  --parse    parse delle pagine in cache -> data.json intermedio (nella
             directory ricerca, gitignored).
  --convert  data.json -> monsters_local.json + npcs_local.json + manifest.
  --write    con --convert: scrive i file (default dry-run).
"""

from __future__ import annotations

import argparse
import json
import re
from urllib.parse import quote
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_fetch import cache_path, fetch

ROOT = Path(__file__).resolve().parents[1]
MONSTERDB_DIR = (
    ROOT.parent.parent / "sessione-2026-07-16" / "ricerca" / "PathfinderMonsterDatabase"
)
EXPANDED_JSON = MONSTERDB_DIR / "data" / "expanded" / "data.json"
LOCAL_DIR = ROOT / "data" / "reference" / "pi_local_only"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"

INDEXES = {
    "monsters": "https://aonprd.com/Monsters.aspx?Letter=All",
    "mythic": "https://aonprd.com/MythicMonsters.aspx?Letter=All",
    "npcs": "https://aonprd.com/NPCs.aspx?SubGroup=All",
}
DISPLAY = {
    "monsters": "MonsterDisplay",
    "mythic": "MythicMonsterDisplay",
    "npcs": "NPCDisplay",
}


def index_urls() -> dict[str, list[str]]:
    """URL delle pagine mostro/NPC dai tre indici AoN (cache)."""
    out = {}
    for kind, url in INDEXES.items():
        html = cache_path(url).read_text(encoding="utf-8", errors="replace")
        found = re.findall(DISPLAY[kind] + r"\.aspx\?ItemName=([^\"&]+)", html)
        seen = []
        for item in found:
            # Gli indici AoN usano forme miste: %20 per alcuni mostri, spazi
            # letterali per gli NPC (urllib rifiuta i control chars). I nomi
            # con apostrofo curvo (U+2019) vanno percent-encodati in UTF-8;
            # safe="%" preserva gli escape gia' presenti (%20, %27).
            item = quote(item, safe="%")
            page_url = f"https://aonprd.com/{DISPLAY[kind]}.aspx?ItemName={item}"
            if page_url not in seen:
                seen.append(page_url)
        out[kind] = seen
    return out


def cmd_fetch() -> int:
    urls = index_urls()
    total = sum(len(v) for v in urls.values())
    ok = fail = 0
    for kind, pages in urls.items():
        for url in pages:
            if cache_path(url).exists():
                ok += 1
                continue
            try:
                fetch(url, delay=2.0, cache=True)
                ok += 1
            except Exception as exc:
                fail += 1
                print(f"FALLITO {kind} {url} {str(exc)[:60]}")
    print(f"fetch: {ok}/{total} ok, {fail} falliti")
    return 0


def _parse_page(html: str, url: str) -> dict:
    """parsePage di PathfinderMonsterDatabase, importata come libreria.

    main.py carica class_hds solo nel blocco __main__: come libreria va
    iniettato (data/class_hds.json nel clone)."""
    sys.path.insert(0, str(MONSTERDB_DIR))
    import main as monsterdb  # noqa: PLC0415 - import lazy voluto

    if not getattr(monsterdb, "class_hds", None):
        monsterdb.class_hds = json.loads(
            (MONSTERDB_DIR / "data" / "class_hds.json").read_text(encoding="utf-8")
        )
    if not getattr(monsterdb, "classname_map", None):
        monsterdb.classname_map = {n.lower(): n for n in monsterdb.class_hds}
    return monsterdb.parsePage(html, url)


def cmd_parse() -> int:
    urls = index_urls()
    objects, failures = {}, []
    for kind, pages in urls.items():
        for url in pages:
            path = cache_path(url)
            if not path.exists():
                failures.append(f"{kind} | {url} | non in cache")
                continue
            try:
                obj = _parse_page(
                    path.read_text(encoding="utf-8", errors="replace"), url
                )
                obj["_kind"] = kind
                objects[url] = obj
            except Exception as exc:
                failures.append(f"{kind} | {url} | {str(exc)[:80]}")
    EXPANDED_JSON.parent.mkdir(parents=True, exist_ok=True)
    EXPANDED_JSON.write_text(json.dumps(objects, ensure_ascii=False), encoding="utf-8")
    print(f"parse: {len(objects)} ok, {len(failures)} falliti")
    for line in failures[:20]:
        print(" ", line)
    if failures:
        (EXPANDED_JSON.parent / "failures.txt").write_text(
            "\n".join(failures) + "\n", encoding="utf-8"
        )
    return 0


def split_and_convert(objects: dict) -> tuple[list, list]:
    """{url: pageObject con _kind} -> (monster_entries, npc_entries).

    monsters+mythic insieme (tag 'mythic' sui mitici), npc a parte (tag 'npc'
    al posto di 'monster'); dedup per nome (tiene il primo, ordine URL)."""
    from tools.import_monsters import convert_monsters

    seen = set()
    monsters, npcs = [], []
    for kinds, out, is_npc in (
        (("monsters", "mythic"), monsters, False),
        (("npcs",), npcs, True),
    ):
        for url, obj in objects.items():
            if obj.get("_kind") not in kinds:
                continue
            for e in convert_monsters([(url, obj)]):
                if e["name"] in seen:
                    continue
                seen.add(e["name"])
                if is_npc:
                    e["tags"] = ["npc" if t == "monster" else t for t in e["tags"]]
                elif obj["_kind"] == "mythic":
                    e["tags"] = e["tags"] + ["mythic"]
                out.append(e)
    return monsters, npcs


def cmd_convert(write: bool) -> int:
    from datetime import date

    objects = json.loads(EXPANDED_JSON.read_text(encoding="utf-8"))
    monsters, npcs = split_and_convert(objects)
    print(f"convert: {len(monsters)} mostri (+mitici), {len(npcs)} npc")
    if not write:
        print("Dry-run: nessuna modifica (usa --write)")
        return 0
    for path, entries in (
        (LOCAL_DIR / "monsters_local.json", monsters),
        (LOCAL_DIR / "npcs_local.json", npcs),
    ):
        path.write_text(
            json.dumps(
                {
                    "_license": "OGL-1.0a",
                    "_source": (
                        "Archives of Nethys via PathfinderMonsterDatabase "
                        "(local only, not redistributed)"
                    ),
                    "entries": entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"scritto {path} ({len(entries)} entry, NON committare)")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    for c in manifest["catalogs"]:
        if c["kind"] == "monsters":
            c["entries"] = len(monsters)
            c["last_verified"] = today
    manifest["catalogs"] = [
        c for c in manifest["catalogs"] if c["kind"] != "npcs_local"
    ]
    manifest["catalogs"].append(
        {
            "file": "pi_local_only/npcs_local.json",
            "kind": "npcs_local",
            "source": "Archives of Nethys (aonprd.com)",
            "license": "OGL-1.0a",
            "is_ogc": False,
            "is_pi": False,
            "cup_allowed": False,
            "local_only": True,
            "entries": len(npcs),
            "notes": "NPC da NPCs.aspx AoN (espansione 2026-07-25). NON redistribuire.",
            "last_verified": today,
        }
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("manifest aggiornato (monsters + npcs_local)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--parse", action="store_true")
    ap.add_argument("--convert", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        return cmd_fetch()
    if args.parse:
        return cmd_parse()
    if args.convert:
        return cmd_convert(args.write)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
