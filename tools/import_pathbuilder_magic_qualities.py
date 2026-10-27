#!/usr/bin/env python3
"""Import delle qualita' magiche Pathbuilder 1e verso rules-engine-v2
(Fase A ciclo Builder E2E, 2026-08-08 — seguito D4).

Parse di DUE XML in `data/reference/pi_local_only/pathbuilder/` (estratto da
res/raw dell'APK Pathbuilder 1e, BlueStacks dell'utente, permesso concesso
2026-08-02 — dataset PI local-only, MAI committato) ed emissione di UN JSON
committato in `pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-magic-qualities.json — armorMagic (68 qualita' per armature/
  scudi/accessori) + weaponEffects (97 qualita' per armi), catalogo
  nome+categorie. Header _provenance/counts + mappe codici dichiarate.

Perimetro DECISO (dichiarato): le qualita' sono METADATA — nome + categorie
di applicabilita'. NIENTE description (non esiste proprio come campo nel
dato), NIENTE bonus/prezzi inventati (il costo delle qualita' non e' nel
dato: MAI dedotto). Il <Damage> di 13 weapon effects (es. "(2d6 v Lawful)")
resta stringa grezza strutturata, MAI parsato a effetto meccanico.

Consumatore: NESSUNO ancora (onesto). Candidato dichiarato: la legality
equipaggiamento D6 (legality.ts) per il canale "qualita' magiche ammesse
sull'item" — i dati sono pronti, il wiring e' un seguito. Il canale
`proficiency` attuale NON usa questi dati.

Formato (ricognizione 2026-08-08):
- data_armor_magic.xml (68 righe): <Effect>, <Categories> codici separati
  da '&' con la STESSA codifica di data_armor.xml (0 leggera, 1 media,
  2 pesante, 3 scudo, 4 scudo torre, 5 accessorio magico — i "Bracers of
  Armor", vedi import_pathbuilder_equipment.py). 57 qualita' su tutte le
  armature (0&1&2), 34 scudo, 33 torre, 26 accessorio. Nessun duplicato.
- data_weapon_effects.xml (97 righe): <Name>, <Categories> con la codifica
  di data_weapons.xml (0 leggera, 1 a una mano, 2 a due mani, 3 da tiro,
  4 da fuoco a una mano, 5 da fuoco a due mani, 6 naturale). <Damage>
  opzionale su 13 righe (anarchic/axiomatic/holy/unholy, flaming burst...).

Uso:
  python tools/import_pathbuilder_magic_qualities.py                 # scrive
  python tools/import_pathbuilder_magic_qualities.py --report-only   # stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

# Mappe codici DICHIARATE: identiche a quelle di import_pathbuilder_equipment
# (D4) — le riusiamo per coerenza, verificate sui membri noti (Animated 3&4 =
# scudo/torre, Bashing 3 = solo scudo; Keen 0&1&2&6 = mischia+naturale).
ARMOR_CATEGORIES = {
    0: "light",
    1: "medium",
    2: "heavy",
    3: "shield",
    4: "tower-shield",
    5: "magic-accessory",
}
WEAPON_CATEGORIES = {
    0: "light",
    1: "one-handed",
    2: "two-handed",
    3: "ranged",
    4: "firearm-one-handed",
    5: "firearm-two-handed",
    6: "natural",
}

OUTPUT_FILE = "pathbuilder-magic-qualities.json"


def _rows(path: Path) -> list[ET.Element]:
    return ET.parse(path).getroot().findall("Row")


def _categories(row: ET.Element, labels: dict[int, str]) -> dict:
    raw = (row.findtext("Categories") or "").strip()
    codes = [int(c) for c in raw.split("&") if c.strip()]
    return {"categories": codes, "categoryLabels": [labels[c] for c in codes]}


def import_armor_magic(raw_dir: Path) -> list[dict]:
    out = []
    for row in _rows(raw_dir / "data_armor_magic.xml"):
        out.append(
            {
                "name": (row.findtext("Effect") or "").strip(),
                **_categories(row, ARMOR_CATEGORIES),
                # MAI description/damage: non esistono come campi nel dato
            }
        )
    return out


def import_weapon_effects(raw_dir: Path) -> list[dict]:
    out = []
    for row in _rows(raw_dir / "data_weapon_effects.xml"):
        entry = {
            "name": (row.findtext("Name") or "").strip(),
            **_categories(row, WEAPON_CATEGORIES),
        }
        damage = (row.findtext("Damage") or "").strip()
        if damage:
            # stringa grezza strutturata (es. "(2d6 v Lawful)"), MAI parsata
            entry["damage"] = damage
        out.append(entry)
    return out


def build(raw_dir: Path) -> dict:
    raw_dir = Path(raw_dir)
    armor_magic = import_armor_magic(raw_dir)
    weapon_effects = import_weapon_effects(raw_dir)
    return {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), "
            "data_armor_magic.xml + data_weapon_effects.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_magic_qualities.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a.",
            "desc_policy": "Solo nomi + categorie di applicabilita'. NIENTE "
            "description (non esiste nel dato), NIENTE bonus/prezzi "
            "inventati (non nel dato). Il <Damage> di 13 weapon "
            "effects resta stringa grezza, MAI parsato.",
            "mapping_policy": "Le mappe codici (armorCategories, weaponCategories) "
            "sono quelle DICHIARATE di import_pathbuilder_equipment "
            "(D4), riusate per coerenza.",
            "consumer": "NESSUN consumatore ancora (dichiarato): dataset pronto "
            "per il candidato legality equipaggiamento D6 (qualita' "
            "magiche ammesse sull'item). Il canale `proficiency` "
            "attuale NON usa questi dati.",
        },
        "armorCategories": {str(k): v for k, v in ARMOR_CATEGORIES.items()},
        "weaponCategories": {str(k): v for k, v in WEAPON_CATEGORIES.items()},
        "counts": {
            "armorMagic": len(armor_magic),
            "weaponEffects": len(weapon_effects),
        },
        "armorMagic": armor_magic,
        "weaponEffects": weapon_effects,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    payload = build(Path(args.raw_dir))
    counts = payload["counts"]
    with_damage = sum(1 for e in payload["weaponEffects"] if "damage" in e)
    print(f"qualita' armatura/scudi: {counts['armorMagic']}")
    print(
        f"qualita' armi: {counts['weaponEffects']} "
        f"(con Damage grezzo: {with_damage})"
    )

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / OUTPUT_FILE
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
