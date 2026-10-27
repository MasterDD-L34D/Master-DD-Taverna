#!/usr/bin/env python3
"""Import dei dataset Pathbuilder 1e "equipaggiamento" verso rules-engine-v2
(slice D4).

Parse di TRE XML in `data/reference/pi_local_only/pathbuilder/` (estratto da
res/raw dell'APK Pathbuilder 1e, BlueStacks dell'utente, permesso concesso
2026-08-02 — dataset PI local-only, MAI committato) ed emissione di UN JSON
committato in `pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-equipment.json — weapons (313) + armor (58) + slotted (2.783)
  con le sole meccaniche STRUTTURATE nel dato. Header _provenance/counts/
  report + mappe codici dichiarate.

Disciplina OGL/PI identica a import_pathbuilder_races.py (D1): solo nomi +
meccaniche strutturate. MAI esportata la Description degli oggetti slotted
(testo Paizo) ne' il Ref (URL d20pfsrd): restano nel dataset locale.

Note di formato (ricognizione 2026-08-07):

- data_weapons.xml (313 righe): <Weapon>, <DamageType> (S/P/B e combo
  "B and P" / "P or S"; '0' = nessun danno), <Proficiency> (-1 naturale/
  disarmato, 0 semplice, 1 da guerra, 2 esotica, 3 da fuoco), <Category>
  (0 leggera, 1 a una mano, 2 a due mani, 3 da tiro, 4 da fuoco a una mano,
  5 da fuoco a due mani, 6 naturale), <Damage> ('-1' = nessun danno: touch
  attack, reti, blast cinetici — 11 righe), <CritRange> (MINIMO del dado:
  19 = 19-20; -1 = nessun critico), <CritMultiplier>, <Finessable>,
  <WeaponGroup> (gruppi separati da '&'), <Hands> (0 = una mano/leggera,
  1 = due mani), <RangeIncrement> (0 = n/a, 26 righe senza il campo),
  <UsesAmmo> (12 righe), <naturalWeapon> (FALSE/false/true/TRUE).
  NESSUN costo/peso nel dato: non esistono proprio come campi, MAI inventati
  (il catalogo unificato li prende da PCGen dove presenti).
- data_armor.xml (58 righe): <Armor>, <Bonus>, <MaxDex> (99 = nessun cap ->
  null), <CheckPenalty> (MAGNITUDINE positiva: 5 = ACP -5 RAW — il segno
  meno e' applicato in export), <Arcane_Spell> (frazione: 0.3 = 30%),
  <Speed_30ft> (-1 = n/a, scudi -> null), <Weight1>, <Category> (0 leggera,
  1 media, 2 pesante, 3 scudo, 4 scudo torre, 5 accessorio magico — le 8
  righe "Bracers of Armor +N"). NESSUN costo nel dato.
- data_equipment_slotted.xml (2.855 righe): <Name>, <Cost> (mo, anche
  frazionario: 0.01), <Ref> (URL d20pfsrd — mai esportato), <Slot> (codice
  numerico 0-25), <Description>
  (testo Paizo PI — MAI esportato), <Source>, <Finished>. 72 righe SENZA
  Name sono template di bonus (EffectType/BonusType/Amount), non oggetti:
  saltate e conteggiate (slottedUnnamedSkipped). 11 righe con Name non hanno
  Slot (es. Amulet of the Bloodied): slot/slotLabel null DICHIARATI.
  Tutte le righe con Name
  hanno Finished=Yes (verificato). 6 nomi compaiono due volte con slot/
  fonte diversi: entrambe le voci restano, duplicati dichiarati nel report.
  I campi BonusType/Amount (274 righe) NON entrano nel JSON: l'enhancement
  resta preset di nome+stat base, MAI bonus inventato (regola del piano D4).
- Armi doppie (2 nel dataset: Gnome hooked hammer, Taiaha): Damage e
  CritMultiplier sono per estremita', separati da '&' (es. "1d8&1d6",
  "3&4"). damage resta la stringa grezza strutturata; critMultiplier singolo
  e' null DICHIARATO e la coppia va in critMultipliers.
- Mappa slot: i codici 0-11 sono gli slot corporei PF (belt..slotless),
  12-25 gruppi di catalogo PB (ring, rod, staff, gear, book, tool, religioso,
  outfit, componente alchemico, accessorio animale, pozione, scroll, wand,
  munizione). Etichette DICHIARATE, derivate da ispezione dei membri di
  ogni codice (non da documentazione PB, assente).

Uso:
  python tools/import_pathbuilder_equipment.py                 # scrive il JSON
  python tools/import_pathbuilder_equipment.py --report-only   # solo stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

# Mappe DICHIARATE (codici numerici PB -> etichette), derivate da ispezione
# dei membri di ogni codice (ricognizione 2026-08-07), non da documentazione
# Pathbuilder (assente). Verificate sui RAW noti: Handaxe cat 0 (leggera),
# Battleaxe cat 1 (una mano), Greataxe cat 2 (due mani), Longbow cat 3,
# pistole cat 4, moschetti cat 5, Bite/Claw cat 6; Sickle prof 0 (semplice),
# Longsword prof 1 (da guerra), Bastard sword prof 2 (esotica), armi da
# fuoco prof 3, Bite/Unarmed prof -1.
WEAPON_CATEGORIES = {
    0: "light",
    1: "one-handed",
    2: "two-handed",
    3: "ranged",
    4: "firearm-one-handed",
    5: "firearm-two-handed",
    6: "natural",
}
WEAPON_PROFICIENCIES = {
    -1: "none",
    0: "simple",
    1: "martial",
    2: "exotic",
    3: "firearm",
}
ARMOR_CATEGORIES = {
    0: "light",
    1: "medium",
    2: "heavy",
    3: "shield",
    4: "tower-shield",
    5: "magic-accessory",
}

# Slot slotted: 0-11 = slot corporei PF (verificati sui membri: cinture -> 0,
# robe/bodywrap -> 1, vesti/baldric -> 2, lenti -> 3, stivali -> 4, guanti ->
# 5, elmi/crown -> 6, fasce -> 7, amuleti -> 8, mantelli -> 9, bracciali ->
# 10, meravigliosi senza slot -> 11). 12-25 = gruppi di catalogo PB
# (anelli -> 12, verghe -> 13, bastoni -> 14, equipaggiamento -> 15, libri ->
# 16, attrezzi/lucchetti/chiavi -> 17, simboli sacri -> 18, vestiti -> 19,
# componenti alchemici -> 20, accessori animali -> 21, pozioni -> 22,
# pergamene -> 23, bacchette -> 24, munizioni -> 25).
SLOT_LABELS = {
    0: "belt",
    1: "body",
    2: "chest",
    3: "eyes",
    4: "feet",
    5: "hands",
    6: "head",
    7: "headband",
    8: "neck",
    9: "shoulders",
    10: "wrists",
    11: "slotless",
    12: "ring",
    13: "rod",
    14: "staff",
    15: "adventuring-gear",
    16: "book",
    17: "tool",
    18: "religious-item",
    19: "outfit",
    20: "alchemical-component",
    21: "animal-gear",
    22: "potion",
    23: "scroll",
    24: "wand",
    25: "ammunition",
}


def _rows(path: Path) -> list[ET.Element]:
    return ET.parse(path).getroot().findall("Row")


def _int(row: ET.Element, field: str) -> int | None:
    text = row.findtext(field)
    if text is None or not text.strip():
        return None
    return int(text)


def _bool(row: ET.Element, field: str) -> bool | None:
    text = row.findtext(field)
    if text is None:
        return None
    return text.strip().lower() == "true"


def import_weapons(raw_dir: Path) -> list[dict]:
    out = []
    for row in _rows(raw_dir / "data_weapons.xml"):
        damage = (row.findtext("Damage") or "").strip() or None
        if damage == "-1":
            damage = None  # nessun danno nel dato: dichiarato assente
        damage_type = (row.findtext("DamageType") or "").strip() or None
        if damage_type == "0":
            damage_type = None
        crit_range = _int(row, "CritRange")
        if crit_range == -1:
            crit_range = None  # nessun critico nel dato
        crit_raw = (row.findtext("CritMultiplier") or "").strip()
        crit_mult: int | None = None
        crit_mults: list[int] | None = None
        if "&" in crit_raw:
            # arma doppia: un moltiplicatore per estremita' (es. "3&4")
            crit_mults = [int(p) for p in crit_raw.split("&")]
        elif crit_raw and crit_raw != "-1":
            crit_mult = int(crit_raw)
        range_inc = _int(row, "RangeIncrement")
        if range_inc == 0:
            range_inc = None  # 0 = n/a (armi da mischia)
        category = _int(row, "Category")
        proficiency = _int(row, "Proficiency")
        hands_code = _int(row, "Hands")
        group = (row.findtext("WeaponGroup") or "").strip()
        out.append(
            {
                "name": (row.findtext("Weapon") or "").strip(),
                "category": category,
                "categoryLabel": WEAPON_CATEGORIES[category],
                "proficiency": proficiency,
                "proficiencyLabel": WEAPON_PROFICIENCIES[proficiency],
                "damage": damage,
                "damageType": damage_type,
                "critRange": crit_range,
                "critMultiplier": crit_mult,
                **({"critMultipliers": crit_mults} if crit_mults else {}),
                "finesse": bool(_bool(row, "Finessable")),
                "weaponGroups": (
                    [] if group in ("", "0") else [g for g in group.split("&") if g]
                ),
                # Hands PB: 0 = una mano o leggera, 1 = due mani
                "hands": 2 if hands_code == 1 else 1,
                "rangeIncrement": range_inc,
                "usesAmmo": _bool(row, "UsesAmmo"),
                "naturalWeapon": bool(_bool(row, "naturalWeapon")),
            }
        )
    return out


def import_armor(raw_dir: Path) -> list[dict]:
    out = []
    for row in _rows(raw_dir / "data_armor.xml"):
        max_dex = _int(row, "MaxDex")
        if max_dex == 99:
            max_dex = None  # 99 = nessun cap (convenzione PB): null dichiarato
        check_penalty = _int(row, "CheckPenalty") or 0
        speed = _int(row, "Speed_30ft")
        if speed == -1:
            speed = None  # -1 = n/a (scudi): null dichiarato
        arcane_raw = (row.findtext("Arcane_Spell") or "0").strip()
        category = _int(row, "Category")
        out.append(
            {
                "name": (row.findtext("Armor") or "").strip(),
                "category": category,
                "categoryLabel": ARMOR_CATEGORIES[category],
                "acBonus": _int(row, "Bonus"),
                "maxDex": max_dex,
                # PB memorizza la MAGNITUDINE positiva: 5 = ACP -5 RAW
                "armorCheckPenalty": -check_penalty,
                # Arcane_Spell e' una frazione: 0.3 = 30%
                "arcaneSpellFailure": round(float(arcane_raw) * 100),
                "speed30ft": speed,
                "weight": _int(row, "Weight1"),
            }
        )
    return out


def import_slotted(raw_dir: Path) -> tuple[list[dict], int]:
    """(voci con Name, righe senza Name saltate — template di bonus)."""
    out = []
    skipped = 0
    for row in _rows(raw_dir / "data_equipment_slotted.xml"):
        name = (row.findtext("Name") or "").strip()
        if not name:
            skipped += 1  # template di bonus (BonusType/Amount), non oggetto
            continue
        slot = _int(row, "Slot")
        source = (row.findtext("Source") or "").strip() or None
        cost_raw = (row.findtext("Cost") or "").strip().replace(",", "")
        # nel dato: anche frazionario (0.01) e una riga con separatore
        # migliaia ("25,000" -> 25000)
        cost = float(cost_raw) if cost_raw else None
        if cost is not None and cost.is_integer():
            cost = int(cost)
        out.append(
            {
                "name": name,
                "cost": cost,  # mo, anche frazionario nel dato (es. 0.01)
                # 11 righe con Name non hanno Slot (es. Amulet of the Bloodied):
                # slot/slotLabel null DICHIARATI, mai dedotti
                "slot": slot,
                "slotLabel": SLOT_LABELS[slot] if slot is not None else None,
                "source": source,
                # MAI: Description (PI), Ref (URL PI), BonusType/Amount
                # (enhancement = preset di nome, mai bonus inventato)
            }
        )
    return out, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    weapons = import_weapons(raw_dir)
    armor = import_armor(raw_dir)
    slotted, slotted_skipped = import_slotted(raw_dir)

    without_damage = [w["name"] for w in weapons if w["damage"] is None]
    slotted_name_counts = Counter(i["name"] for i in slotted)
    slotted_dups = sorted(n for n, c in slotted_name_counts.items() if c > 1)

    payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), "
            "data_weapons.xml + data_armor.xml + "
            "data_equipment_slotted.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_equipment.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. Description "
            "degli oggetti e Ref (URL d20pfsrd): Product Identity — MAI "
            "esportati (restano nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo nomi + meccaniche strutturate, MAI la Description "
            "degli oggetti slotted ne' il Ref. BonusType/Amount degli "
            "slotted NON esportati: enhancement magici = preset di "
            "nome + stat base, MAI bonus inventato (piano D4).",
            "mapping_policy": "Le mappe codici numerici PB (weaponCategories, "
            "weaponProficiencies, armorCategories, slotLabels) "
            "sono DICHIARATE qui, derivate da ispezione dei "
            "membri di ogni codice — non da documentazione "
            "Pathbuilder (assente).",
            "conflict_policy": "PCGen (pcgen-equipment.json) VINCE sui valori per "
            "i nomi duplicati; PB aggiunge copertura (nomi "
            "assenti da PCGen). Match solo per nome normalizzato "
            "esatto: varianti di naming (es. 'Heavy steel "
            "shield' PB vs 'Shield (Heavy, Steel)' PCGen) NON "
            "sono fuse — dichiarato, mai merge silenzioso.",
            "format_notes_doc": "tools/import_pathbuilder_equipment.py (docstring)",
        },
        "weaponCategories": {str(k): v for k, v in WEAPON_CATEGORIES.items()},
        "weaponProficiencies": {str(k): v for k, v in WEAPON_PROFICIENCIES.items()},
        "armorCategories": {str(k): v for k, v in ARMOR_CATEGORIES.items()},
        "slotLabels": {str(k): v for k, v in SLOT_LABELS.items()},
        "counts": {
            "weapons": len(weapons),
            "weaponsWithDamage": len(weapons) - len(without_damage),
            "armor": len(armor),
            "slotted": len(slotted),
            "slottedUnnamedSkipped": slotted_skipped,
            "slottedDuplicateNames": len(slotted_dups),
        },
        "report": {
            "weaponsWithoutDamage": without_damage,
            "slottedDuplicateNames": slotted_dups,
        },
        "weapons": weapons,
        "armor": armor,
        "slotted": slotted,
    }

    print(
        f"armi: {len(weapons)} (con danno: "
        f"{payload['counts']['weaponsWithDamage']}; senza danno dichiarato: "
        f"{len(without_damage)})"
    )
    print(f"armature/scudi: {len(armor)}")
    print(
        f"oggetti slotted: {len(slotted)} "
        f"(righe template senza nome saltate: {slotted_skipped}; "
        f"nomi duplicati dichiarati: {slotted_dups})"
    )

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "pathbuilder-equipment.json"
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
