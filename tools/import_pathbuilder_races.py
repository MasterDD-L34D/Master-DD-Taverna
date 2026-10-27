#!/usr/bin/env python3
"""Import dei dataset Pathbuilder 1e "razze" verso rules-engine-v2 (slice D1).

Parse di DUE XML in `data/reference/pi_local_only/pathbuilder/` (estratto da
res/raw dell'APK Pathbuilder 1e, BlueStacks dell'utente, permesso concesso
2026-08-02 — dataset PI local-only, MAI committato) ed emissione di DUE JSON
committati in `pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-races.json — le 74 razze di data_races.xml (669 righe-trait):
  name, size, abilityAdjustments (SOLO se parsati dal dato, altrimenti null
  dichiarato), flag flexible, playable (lista esplicita, non euristica),
  source.
- pathbuilder-race-traits.json — i 702 tratti razziali alternativi di
  data_races_alternative_traits.xml (59 razze): race, trait, replaces[],
  changes[], source.

Disciplina OGL/PI identica a import_pathbuilder_raw.py (PB-1): solo nomi +
meccaniche strutturate. MAI esportata la Description dei tratti (testo Paizo,
resta nel dataset locale). Il catalogo curato
`src/data/races.json` (26 razze) RESTA INTATTO e vince sempre: questo dataset
e' additivo, nessuna scrittura sul curato.

Note di formato (ricognizione 2026-08-07):

- <Race> compare SOLO sulla prima riga del blocco razza; le righe seguenti
  sono i tratti di quella razza (Trait/Description/ShowInSpecials/HasEffect).
- <Src> (races) / <Source> (alternative traits) compare solo su alcune righe
  ma e' uniforme per razza; il blocco Human non ha Src: source null dichiarato.
- Taglia: un tratto il cui nome e' una categoria di taglia (Medium, Small,
  Large...). 22 razze non hanno tratto taglia (voci da bestiari/race builder):
  size null dichiarata, mai dedotta.
- Ability adjustments: NON un campo strutturato, vivono nella Description del
  tratto "Ability Bonus". Parsati SOLO i formati regolari con segno+numero
  ADIACENTE al nome caratteristica ("+2 Constitution", "–2 Charisma",
  "+2 Str"; il segno meno puo' essere U+2013/U+2212/ASCII). Forme non
  adiacenti ("a +2 bonus to Wisdom", "a +2 racial bonus to either Strength,
  Dexterity, or Constitution") NON sono parsate: abilityAdjustments null
  dichiarato (59 razze su 74, elencate nel report del JSON).
- Razze "flex" ("+2 to One Ability Score"): Human, Half-Elf, Half-Orc — flag
  flexible dichiarato, coerente col contratto E6-A6 del converter (+2 a
  scelta via sheet_payload.bonus_razziale_flessibile) e con
  FLEXIBLE_RACE_NAMES di apps/web PointBuyTable.
- ReplacedTraits/ChangedTraits: nomi di tratti separati da '&'.

Uso:
  python tools/import_pathbuilder_races.py                 # scrive i due JSON
  python tools/import_pathbuilder_races.py --report-only   # solo stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
  --no-strict-playable   (non validare la lista giocabili contro il dataset)
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

SEP_LIST = "&"

SIZES = {
    "Fine": "fine",
    "Diminutive": "diminutive",
    "Tiny": "tiny",
    "Small": "small",
    "Medium": "medium",
    "Large": "large",
    "Huge": "huge",
    "Gargantuan": "gargantuan",
    "Colossal": "colossal",
}

# Razze giocabili PC: LISTA ESPLICITA (regola del piano D1: dato, non
# euristica). Sono le 7 razze core del CRB piu' le 30 dell'Advanced Race
# Guide (16 featured + 14 uncommon) — l'elenco ufficiale Paizo di razze PC.
# NOTA: nel dataset PB anche Lizardfolk e Gnoll hanno Src=ARG, ma sono
# schede d'esempio del race builder (tratti con "(N RP)"): la lista
# esplicita le esclude, un filtro per Src non potrebbe.
PLAYABLE_PC_RACES = frozenset(
    [
        # CRB (core)
        "Dwarf",
        "Elf",
        "Gnome",
        "Half-Elf",
        "Half-Orc",
        "Halfling",
        "Human",
        # ARG featured
        "Aasimar",
        "Catfolk",
        "Dhampir",
        "Drow",
        "Fetchling",
        "Goblin",
        "Hobgoblin",
        "Ifrit",
        "Kobold",
        "Orc",
        "Oread",
        "Ratfolk",
        "Sylph",
        "Tengu",
        "Tiefling",
        "Undine",
        # ARG uncommon
        "Changeling",
        "Duergar",
        "Gillman",
        "Grippli",
        "Kitsune",
        "Merfolk",
        "Nagaji",
        "Samsaran",
        "Strix",
        "Suli",
        "Svirfneblin",
        "Vanara",
        "Vishkanya",
        "Wayang",
    ]
)

# Segno+numero ADIACENTE al nome caratteristica (pieno o sigla). Il meno
# nei dati e' spesso U+2013 (–); accettati anche U+2212 e ASCII '-'.
ABILITY_BONUS_RE = re.compile(
    r"([+\u2013\u2212-])\s*(\d+)\s*"
    r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma"
    r"|Str|Dex|Con|Int|Wis|Cha)\b"
)
FLEXIBLE_RE = re.compile(
    r"\+\s*2\s+to\s+(?:one|any\s+one)\s+ability\s+score", re.IGNORECASE
)

ABILITY_KEYS = {
    "strength": "str",
    "dexterity": "dex",
    "constitution": "con",
    "intelligence": "int",
    "wisdom": "wis",
    "charisma": "cha",
    "str": "str",
    "dex": "dex",
    "con": "con",
    "int": "int",
    "wis": "wis",
    "cha": "cha",
}


def parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def iter_rows(root: ET.Element) -> list[ET.Element]:
    return root.findall("Row")


def parse_ability_bonus(description: str | None) -> dict | None:
    """Parsa gli aggiustamenti SOLO dal formato regolare segno+numero+nome.

    Ritorna None (dichiarato assente) se la description non contiene numeri
    adiacenti a un nome caratteristica: mai inventati."""
    if not description:
        return None
    out: dict[str, int] = {}
    for sign, num, ability in ABILITY_BONUS_RE.findall(description):
        key = ABILITY_KEYS[ability.lower()]
        value = int(num) * (1 if sign == "+" else -1)
        out[key] = value
    return out or None


def is_flexible_ability_bonus(description: str | None) -> bool:
    """True per "+2 to One Ability Score" (Human, Half-Elf, Half-Orc)."""
    return bool(description and FLEXIBLE_RE.search(description))


def group_race_blocks(rows: list[ET.Element]) -> dict[str, list[ET.Element]]:
    """Raggruppa le righe per razza: <Race> solo sulla prima riga del blocco."""
    blocks: dict[str, list[ET.Element]] = {}
    current: str | None = None
    for row in rows:
        race = row.findtext("Race")
        if race is not None:
            current = race.strip()
            blocks[current] = []
        if current is None:
            raise ValueError("riga senza blocco razza aperto")
        blocks[current].append(row)
    return blocks


def _size_of(rows: list[ET.Element]) -> str | None:
    for row in rows:
        trait = row.findtext("Trait")
        if trait in SIZES:
            return SIZES[trait]
    return None


def _source_of(rows: list[ET.Element], field: str) -> str | None:
    srcs = {row.findtext(field) for row in rows if row.findtext(field)}
    if len(srcs) > 1:
        raise ValueError(f"source non uniforme nel blocco: {sorted(srcs)}")
    return next(iter(srcs), None)


def import_races(raw_dir: Path, *, strict_playable: bool = True) -> list[dict]:
    rows = iter_rows(ET.parse(raw_dir / "data_races.xml").getroot())
    blocks = group_race_blocks(rows)
    if strict_playable:
        missing = sorted(PLAYABLE_PC_RACES - set(blocks))
        if missing:
            raise ValueError(
                f"razze della lista giocabili assenti nel dataset: {missing}"
            )
    out = []
    for race, race_rows in blocks.items():
        ab_row = next(
            (r for r in race_rows if r.findtext("Trait") == "Ability Bonus"), None
        )
        description = ab_row.findtext("Description") if ab_row is not None else None
        out.append(
            {
                "name": race,
                "size": _size_of(race_rows),
                "abilityAdjustments": parse_ability_bonus(description),
                "flexible": is_flexible_ability_bonus(description),
                "playable": race in PLAYABLE_PC_RACES,
                "source": _source_of(race_rows, "Src"),
            }
        )
    return out


def import_alternative_traits(raw_dir: Path) -> list[dict]:
    rows = iter_rows(ET.parse(raw_dir / "data_races_alternative_traits.xml").getroot())
    blocks = group_race_blocks(rows)
    out = []
    for race, race_rows in blocks.items():
        for row in race_rows:
            split = lambda raw: [p for p in (raw or "").split(SEP_LIST) if p]
            out.append(
                {
                    "race": race,
                    "trait": row.findtext("Trait"),
                    "replaces": split(row.findtext("ReplacedTraits")),
                    "changes": split(row.findtext("ChangedTraits")),
                    "source": row.findtext("Source"),
                }
            )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--no-strict-playable", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    races = import_races(raw_dir, strict_playable=not args.no_strict_playable)
    traits = import_alternative_traits(raw_dir)

    without_ability = [r["name"] for r in races if not r["abilityAdjustments"]]
    without_size = [r["name"] for r in races if r["size"] is None]
    without_source = [r["name"] for r in races if r["source"] is None]

    races_payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), data_races.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_races.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. Description "
            "dei tratti: testo Paizo (Product Identity) — MAI esportato "
            "(resta nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo nomi + meccaniche strutturate, MAI la Description "
            "dei tratti. abilityAdjustments SOLO se parsati dal dato "
            "(formato regolare del tratto 'Ability Bonus'), altrimenti "
            "null dichiarato — mai inventati. Il catalogo curato "
            "races.json (26 razze) RESTA INTATTO e vince sempre: "
            "questo dataset e' additivo.",
            "playable_policy": "playable=true solo per la LISTA ESPLICITA di razze "
            "PC (7 core CRB + 30 ARG featured/uncommon) dichiarata "
            "nell'importer (PLAYABLE_PC_RACES) — non un'euristica. "
            "Le schede race-builder di Lizardfolk/Gnoll (Src=ARG) "
            "restano playable=false.",
            "format_notes_doc": "tools/import_pathbuilder_races.py (docstring)",
        },
        "counts": {
            "races": len(races),
            "playable": sum(1 for r in races if r["playable"]),
            "flexible": sum(1 for r in races if r["flexible"]),
            "withAbilityAdjustments": len(races) - len(without_ability),
        },
        "report": {
            "racesWithoutAbilityData": without_ability,
            "racesWithoutSize": without_size,
            "racesWithoutSource": without_source,
        },
        "races": races,
    }

    traits_payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), "
            "data_races_alternative_traits.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_races.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. Description "
            "dei tratti: testo Paizo (Product Identity) — MAI esportato "
            "(resta nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo race/trait/replaces/changes/source: MAI la "
            "Description dei tratti alternativi.",
            "format_notes_doc": "tools/import_pathbuilder_races.py (docstring)",
        },
        "counts": {
            "races": len({t["race"] for t in traits}),
            "traits": len(traits),
        },
        "traits": traits,
    }

    print(
        f"razze: {len(races)} (giocabili PC: "
        f"{races_payload['counts']['playable']}, flex: "
        f"{races_payload['counts']['flexible']}, con ability strutturati: "
        f"{races_payload['counts']['withAbilityAdjustments']})"
    )
    print(f"razze senza ability nel dato (dichiarate): {len(without_ability)}")
    print(f"razze senza taglia nel dato (dichiarate): {len(without_size)}")
    print(f"razze senza source nel dato (dichiarate): {without_source}")
    print(
        f"tratti alternativi: {len(traits)} "
        f"su {traits_payload['counts']['races']} razze"
    )

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in (
            ("pathbuilder-races.json", races_payload),
            ("pathbuilder-race-traits.json", traits_payload),
        ):
            path = out_dir / name
            path.write_text(
                json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
