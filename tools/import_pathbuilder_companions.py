#!/usr/bin/env python3
"""Import dei dataset Pathbuilder 1e "compagni" verso rules-engine-v2.

Task M7 (pathmaster-dd): parse di QUATTRO XML in
`data/reference/pi_local_only/pathbuilder/` (estratto da res/raw dell'APK
Pathbuilder 1e, BlueStacks dell'utente, permesso concesso 2026-08-02 —
dataset PI local-only, MAI committato) ed emissione di UN JSON committato in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-companions.json — famigli (data_familiars.xml), animali da
  compagnia (data_animals.xml), forme base eidolon
  (data_eidolons_base_forms.xml) ed evoluzioni eidolon
  (data_eidolons_evolutions.xml).

Disciplina OGL/PI identica a import_pathbuilder_raw.py (PB-1): solo
meccaniche + nomi. MAI esportati: descShort/specialAbi dei famigli e la
Description delle evoluzioni (testo Paizo, resta nel dataset locale).

Note di formato (ricognizione 2026-08-06):

- Taglie: indice numerico -2=fine, -1=diminutive, 0=tiny, 1=small,
  2=medium, 3=large, 4=huge (verificato: Cat=0 tiny, Horse=3 large,
  famigli come rospo/pipistrello=-1 diminutive).
- Attacchi parsati (`meleeParsed`/`baseAttacksParsed`): voci separate da
  `&`, campi separati da `£`: `count£name£damage£secondary£x5[£rider]`.
  Il 4o campo e' il flag "attacco secondario" (1 = secondario): combacia
  con l'asterisco nel testo (`2 Hooves* (1d6)` del cavallo, RAW: zoccoli
  secondari). Il 5o campo (valori 1/2) NON e' decodificato in modo
  affidabile: NON esportato. Il rider ("Plus Trip") e' dichiarato, mai
  applicato.
- Attacchi delle base form eidolon: `count£name£damage` (3 campi).
- Punteggi `-1` nei famigli = "—" (nessun punteggio: For degli incorporei,
  Int di vegetali/parassiti/costrutti senza mente, Cos di non morti e
  costrutti). Esportati come null.
- Famigli improved: `improved` + `casterLevel` richiesto + `alignment`:
  metadati dichiarati, il motore non fa gating.
- Eidolon base form: `Fort/Ref/Will` 1 = TS BUONO della forma (RAW: due TS
  buoni scelti dalla forma), 0 = cattivo. `AC` = bonus di armatura naturale
  della forma.

Uso:
  python tools/import_pathbuilder_companions.py                 # scrive il JSON
  python tools/import_pathbuilder_companions.py --report-only   # solo stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

SEP_FIELD = "£"
SEP_LIST = "&"

SIZES = {
    -2: "fine",
    -1: "diminutive",
    0: "tiny",
    1: "small",
    2: "medium",
    3: "large",
    4: "huge",
    5: "gargantuan",
    6: "colossal",
}

GOOD_SAVE_FIELDS = (("Fort", "fort"), ("Ref", "ref"), ("Will", "will"))


def size_of(row: ET.Element, field: str = "size") -> str | None:
    raw = row.findtext(field)
    if raw is None or raw.strip() == "":
        return None
    idx = int(raw)
    if idx not in SIZES:
        raise ValueError(f"taglia sconosciuta {idx} in {row.findtext('name')}")
    return SIZES[idx]


def ability(row: ET.Element, field: str) -> int | None:
    """-1 nel dataset = '—' (nessun punteggio), esportato come null."""
    raw = row.findtext(field)
    if raw is None or raw.strip() == "":
        return None
    value = int(raw)
    return None if value == -1 else value


def parse_attacks(raw: str | None, *, three_fields: bool = False) -> list[dict]:
    """`count£name£damage£secondary£x5[£rider]`, voci separate da `&`.

    Le base form eidolon hanno solo 3 campi (nessun flag secondario)."""
    if not raw:
        return []
    out = []
    for chunk in raw.split(SEP_LIST):
        parts = chunk.split(SEP_FIELD)
        if three_fields:
            if len(parts) < 3:
                raise ValueError(f"attacco base form malformato: {chunk!r}")
            count, name, damage = parts[0], parts[1], parts[2]
            out.append({"count": int(count), "name": name, "damage": damage})
            continue
        if len(parts) < 5:
            raise ValueError(f"attacco malformato: {chunk!r}")
        entry = {
            "count": int(parts[0]),
            "name": parts[1],
            "damage": parts[2],
            "secondary": parts[3] == "1",
        }
        if len(parts) >= 6 and parts[5].strip():
            entry["rider"] = parts[5].strip()
        out.append(entry)
    return out


def speed_text(row: ET.Element, *, capital: bool = False) -> str:
    """Velocita' dichiarata: base + eventuali nuoto/volo/scalata del dataset.

    Le base form eidolon usano i campi con la maiuscola (Speed/Swim/Climb)."""
    parts = []
    base = row.findtext("Speed" if capital else "speed")
    if base and int(base) > 0:
        parts.append(f"{int(base)} ft.")
    fields = (
        (("Fly", "fly"), ("Swim", "swim"), ("Climb", "climb"))
        if capital
        else (
            ("fly", "fly"),
            ("swim", "swim"),
            ("climb", "climb"),
            ("burrow", "burrow"),
        )
    )
    for field, label in fields:
        value = row.findtext(field)
        if value and value.strip() not in ("", "0"):
            try:
                ivalue = int(value)
            except ValueError:
                continue
            if ivalue > 0:
                extra = ""
                maneuver = row.findtext("maneuverability") if field == "fly" else None
                if maneuver:
                    extra = f" ({maneuver})"
                parts.append(f"{label} {ivalue} ft.{extra}")
    return ", ".join(parts)


def import_familiars(raw_dir: Path) -> list[dict]:
    rows = ET.parse(raw_dir / "data_familiars.xml").getroot().findall("Row")
    out = []
    for r in rows:
        hd_raw = r.findtext("hd") or ""
        m = re.match(r"^(\d+)d\d+", hd_raw.strip())
        if not m:
            raise ValueError(f"hd non parsabile per {r.findtext('name')}: {hd_raw!r}")
        entry = {
            "name": r.findtext("name"),
            "improved": r.findtext("improved") == "true",
            "benefit": r.findtext("benefit"),
            "feats": [f for f in (r.findtext("feats") or "").split(SEP_LIST) if f],
            "size": size_of(r),
            "type": (r.findtext("type") or "").strip(),
            "subtype": (r.findtext("subType") or "").strip() or None,
            "senses": (r.findtext("senses") or "").strip() or None,
            "ac": int(r.findtext("ac")),
            "deflection": int(r.findtext("deflection") or 0),
            "hp": int(r.findtext("hp")),
            "hd": int(m.group(1)),
            "saves": {
                "fort": int(r.findtext("fort")),
                "ref": int(r.findtext("ref")),
                "will": int(r.findtext("will")),
            },
            "speed": speed_text(r),
            "attacks": parse_attacks(r.findtext("meleeParsed")),
            "abilities": {
                "str": ability(r, "abiStr"),
                "dex": ability(r, "abiDex"),
                "con": ability(r, "abiCon"),
                "int": ability(r, "abiInt"),
                "wis": ability(r, "abiWis"),
                "cha": ability(r, "abiCha"),
            },
            "bab": int(r.findtext("bab")),
            "sr": int(r.findtext("sr")) if r.findtext("sr") else None,
            "source": r.findtext("source"),
            "url": r.findtext("url"),
        }
        if entry["improved"]:
            cl = r.findtext("casterLevel")
            entry["casterLevel"] = int(cl) if cl else None
            entry["alignment"] = r.findtext("alignment")
        out.append(entry)
    return out


def import_animals(raw_dir: Path) -> list[dict]:
    rows = ET.parse(raw_dir / "data_animals.xml").getroot().findall("Row")
    out = []
    for r in rows:
        level = {
            "size": size_of(r, "levelSize"),
            "naturalArmor": int(r.findtext("levelNaturalAC") or 0),
            "attacks": parse_attacks(r.findtext("levelAttacksParsed")),
            "str": int(r.findtext("levelStr") or 0),
            "dex": int(r.findtext("levelDex") or 0),
            "con": int(r.findtext("levelCon") or 0),
            "specialAttacks": (r.findtext("levelSpecialAttacks") or "").strip() or None,
            "specialQualities": (r.findtext("levelSpecialQualities") or "").strip()
            or None,
        }
        out.append(
            {
                "name": r.findtext("name"),
                "size": size_of(r),
                "speed": speed_text(r),
                "naturalArmor": int(r.findtext("baseAC") or 0),
                "attacks": parse_attacks(r.findtext("baseAttacksParsed")),
                "abilities": {
                    "str": ability(r, "str"),
                    "dex": ability(r, "dex"),
                    "con": ability(r, "con"),
                    "int": ability(r, "int"),
                    "wis": ability(r, "wis"),
                    "cha": ability(r, "cha"),
                },
                "specialQualities": (r.findtext("baseSpecialQualities") or "").replace(
                    SEP_LIST, ", "
                )
                or None,
                "levelOfIncrease": int(r.findtext("levelOfIncrease")),
                "level": level,
                "source": r.findtext("source"),
                "ref": r.findtext("ref"),
            }
        )
    return out


def import_eidolon_base_forms(raw_dir: Path) -> list[dict]:
    rows = ET.parse(raw_dir / "data_eidolons_base_forms.xml").getroot().findall("Row")
    out = []
    for r in rows:
        good = [
            save
            for field, save in GOOD_SAVE_FIELDS
            if (r.findtext(field) or "0") == "1"
        ]
        free = (r.findtext("FreeEvolutions") or "").split(SEP_LIST)
        out.append(
            {
                "name": r.findtext("BaseForm"),
                "size": size_of(r, "Size"),
                "speed": speed_text(r, capital=True),
                "naturalArmor": int(r.findtext("AC") or 0),
                "goodSaves": good,
                "attacks": parse_attacks(r.findtext("Attacks"), three_fields=True),
                "abilities": {
                    "str": int(r.findtext("Str")),
                    "dex": int(r.findtext("Dex")),
                    "con": int(r.findtext("Con")),
                    "int": int(r.findtext("Int")),
                    "wis": int(r.findtext("Wis")),
                    "cha": int(r.findtext("Cha")),
                },
                "freeEvolutions": [f for f in free if f],
                "source": r.findtext("Source"),
            }
        )
    return out


def import_eidolon_evolutions(raw_dir: Path) -> list[dict]:
    rows = ET.parse(raw_dir / "data_eidolons_evolutions.xml").getroot().findall("Row")
    out = []
    for r in rows:
        times = r.findtext("TimesSelectable")
        out.append(
            {
                "name": r.findtext("Evolution"),
                "cost": int(r.findtext("Cost")),
                "timesSelectable": int(times) if times else 1,
                "category": int(r.findtext("Category") or 0),
                "source": r.findtext("Source"),
            }
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    familiars = import_familiars(raw_dir)
    animals = import_animals(raw_dir)
    base_forms = import_eidolon_base_forms(raw_dir)
    evolutions = import_eidolon_evolutions(raw_dir)

    payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), "
            "data_familiars.xml + data_animals.xml + "
            "data_eidolons_base_forms.xml + data_eidolons_evolutions.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_companions.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. Description/"
            "specialAbi/descShort: testo Paizo (Product Identity) — MAI "
            "esportato (resta nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo meccaniche + nomi, come PB-1 (pathbuilder-feats.json). "
            "Rider degli attacchi ('Plus Trip') e specialAttacks/Qualities: "
            "dichiarati, mai applicati dal motore. Il 5o campo degli attacchi "
            "parsati Pathbuilder non e' decodificato: non esportato.",
            "format_notes_doc": "tools/import_pathbuilder_companions.py (docstring)",
        },
        "counts": {
            "familiars": len(familiars),
            "animals": len(animals),
            "eidolonBaseForms": len(base_forms),
            "eidolonEvolutions": len(evolutions),
        },
        "familiars": familiars,
        "animals": animals,
        "eidolonBaseForms": base_forms,
        "eidolonEvolutions": evolutions,
    }

    print(
        f"famigli: {len(familiars)} (improved: "
        f"{sum(1 for f in familiars if f['improved'])})"
    )
    print(f"animali da compagnia: {len(animals)}")
    print(
        f"eidolon base forms: {len(base_forms)} -> "
        f"{[f['name'] for f in base_forms]}"
    )
    print(f"eidolon evolutions: {len(evolutions)}")

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "pathbuilder-companions.json"
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
