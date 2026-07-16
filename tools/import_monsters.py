#!/usr/bin/env python3
"""Importa mostri da PathfinderMonsterDatabase nel catalogo reference locale.

Uso tipico (dopo aver clonato PathfinderMonsterDatabase e generato data.json):

    python tools/import_monsters.py \\
        --source-dir ../../sessione-2026-07-16/ricerca/PathfinderMonsterDatabase \\
        --input data/poc/data.json \\
        --output data/reference/pi_local_only/monsters_local.json

L'output e' un catalogo reference compatibile con header `_license` e `_source`.
I dati vanno in `data/reference/pi_local_only/` (gia' .gitignore): non vengono
commessi perche' derivati da Archives of Nethys.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "reference" / "pi_local_only" / "monsters_local.json"


def _source_id(name: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"monster:{safe}"


def _url(name: str) -> str:
    safe = name.replace(" ", "%20")
    return f"https://aonprd.com/MonsterDisplay.aspx?ItemName={safe}"


def _statblock(m: dict) -> str:
    parts = [f"CR {m.get('CR', '?')}", f"XP {m.get('XP', '?')}"]
    align = m.get("alignment", {})
    align_clean = align.get("cleaned", "") if isinstance(align, dict) else str(align)
    size = m.get("size", "?")
    mtype = m.get("type", "")
    parts.append(f"{align_clean} {size} {mtype}".strip())
    hp = m.get("HP", {})
    if isinstance(hp, dict):
        parts.append(f"HP {hp.get('total', '?')} ({hp.get('long', '')})")
    ac = m.get("AC", {})
    if isinstance(ac, dict):
        parts.append(f"AC {ac.get('AC', '?')}, touch {ac.get('touch', '?')}, flat-footed {ac.get('flat_footed', '?')}")
    saves = m.get("saves", {})
    if isinstance(saves, dict):
        parts.append(f"Fort {saves.get('fort', '?')}, Ref {saves.get('ref', '?')}, Will {saves.get('will', '?')}")
    attacks = m.get("attacks", {})
    if isinstance(attacks, dict):
        for atk_type, atk_list in attacks.items():
            if atk_type == "special":
                parts.append(f"Special Attacks: {', '.join(str(a) for a in atk_list)}")
            else:
                texts = []
                for group in atk_list:
                    for entry in group:
                        texts.append(entry.get("text", ""))
                if texts:
                    parts.append(f"{atk_type.capitalize()}: {', '.join(texts)}")
    return "; ".join(p for p in parts if p)


def _clean_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8")


def convert_monsters(input_path: Path, limit: int | None = None) -> list[dict]:
    raw = input_path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        data = json.loads(raw.decode("cp1252", errors="replace"))

    entries = []
    for url, monster in data.items():
        name = monster.get("title1", monster.get("title2", "Unknown"))
        sources = monster.get("sources", [{}])
        source = sources[0].get("name", "Pathfinder RPG Bestiary") if sources else "Pathfinder RPG Bestiary"
        source_page = sources[0].get("page", "") if sources else ""
        tags = ["monster", monster.get("type", ""), monster.get("size", "")]
        alignment = monster.get("alignment", {})
        align_clean = alignment.get("cleaned", "") if isinstance(alignment, dict) else str(alignment)
        if align_clean:
            tags.append(align_clean)
        for subtype in monster.get("subtypes", []):
            tags.append(subtype)
        tags = [t for t in tags if t]

        desc_parts = []
        if monster.get("desc_short"):
            desc_parts.append(_clean_text(monster["desc_short"]))
        if monster.get("desc_long"):
            desc_parts.append(_clean_text(monster["desc_long"]))
        stat = _statblock(monster)
        if stat:
            desc_parts.append("Statblock: " + _clean_text(stat))

        entries.append({
            "name": name,
            "source": source,
            "source_id": _source_id(name),
            "prerequisites": [],
            "tags": tags,
            "references": [_clean_text(f"{source}{f' p. {source_page}' if source_page else ''}")],
            "reference_urls": [_url(name)],
            "description": "\n\n".join(desc_parts),
            "notes": _clean_text(f"Converted from PathfinderMonsterDatabase ({url})"),
        })
        if limit and len(entries) >= limit:
            break
    return entries


def _find_data_json(source_dir: Path, letter: str | None) -> Path | None:
    candidates = []
    if letter:
        candidates.append(source_dir / "data" / letter / "data.json")
    candidates.extend([
        source_dir / "data" / "poc" / "data.json",
        source_dir / "data" / "data.json",
    ])
    for c in candidates:
        if c.exists():
            return c
    return None


def _clone_pathfinder_monster_db(target: Path) -> Path:
    url = "https://github.com/c0d3rman/PathfinderMonsterDatabase.git"
    print(f"Clonazione di PathfinderMonsterDatabase in {target} ...")
    subprocess.run(["git", "clone", "--depth", "1", url, str(target)], check=True)
    return target


def main():
    ap = argparse.ArgumentParser(description="Importa mostri da PathfinderMonsterDatabase")
    ap.add_argument("--source-dir", type=Path, help="Directory del clone di PathfinderMonsterDatabase")
    ap.add_argument("--input", type=Path, help="Path specifico a data.json (sovrascrive l'auto-ricerca)")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path di output")
    ap.add_argument("--letter", help="Lettera sottodirectory in data/ da usare")
    ap.add_argument("--limit", type=int, help="Numero massimo di mostri da importare")
    ap.add_argument("--clone", action="store_true", help="Clona PathfinderMonsterDatabase se --source-dir non esiste")
    args = ap.parse_args()

    source_dir = args.source_dir
    if source_dir is None:
        default_clone = REPO_ROOT.parent.parent / "sessione-2026-07-16" / "ricerca" / "PathfinderMonsterDatabase"
        if default_clone.exists():
            source_dir = default_clone
        elif args.clone:
            source_dir = default_clone
            source_dir.parent.mkdir(parents=True, exist_ok=True)
            _clone_pathfinder_monster_db(source_dir)
        else:
            sys.exit("ERRORE: specifica --source-dir o usa --clone")

    if not source_dir.exists():
        if args.clone:
            source_dir.parent.mkdir(parents=True, exist_ok=True)
            _clone_pathfinder_monster_db(source_dir)
        else:
            sys.exit(f"ERRORE: directory non trovata: {source_dir}")

    if args.input:
        data_json = args.input
        if not data_json.is_absolute():
            data_json = source_dir / data_json
    else:
        data_json = _find_data_json(source_dir, args.letter)
        if data_json is None:
            sys.exit(f"ERRORE: data.json non trovato in {source_dir}/data/")

    print(f"Lettura mostri da: {data_json}")
    entries = convert_monsters(data_json, limit=args.limit)
    if not entries:
        sys.exit("ERRORE: nessun mostro trovato nel file di input")

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = {
        "_license": "OGL-1.0a",
        "_source": "PathfinderMonsterDatabase / Archives of Nethys (local only, not redistributed)",
        "entries": entries,
    }
    out_text = json.dumps(catalog, indent=2, ensure_ascii=False)
    out_text = out_text.encode("utf-8", errors="replace").decode("utf-8")
    output_path.write_text(out_text, encoding="utf-8")
    print(f"Scritti {len(entries)} mostri in: {output_path}")
    print("NOTA: i dati restano in pi_local_only/ e non vanno commessi.")


if __name__ == "__main__":
    main()
