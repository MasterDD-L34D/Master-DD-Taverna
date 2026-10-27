#!/usr/bin/env python3
"""Import dei background traits Pathbuilder 1e verso rules-engine-v2 (C1).

Parse di `data_background_traits.xml` (1.569 voci) in
`data/reference/pi_local_only/pathbuilder/` (estratto da res/raw dell'APK
Pathbuilder 1e, BlueStacks dell'utente — dataset PI local-only, MAI
committato) ed emissione di UN JSON committato in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-background-traits.json — per voce: {name, category}.
  SOLO nome + categoria. MAI la <Description> (testo Paizo PI, resta nel
  dataset locale), MAI la <Ref> (URL d20pfsrd). Stessa disciplina OGL degli
  import D1/D2 (races/archetypes).

Perimetro dichiarato (contratto C1): il catalogo serve a RICONOSCERE i
tratti nelle build importate (chiudere il gap "trait" del report B1: 126
entita' / 124 build). Gli EFFETTI dei tratti restano non modellati: sono
quasi tutti bonus situazionali/testuali — dichiarato nel converter
(pathbuilder-v2.ts), mai un bonus inventato.

Mappa codice <Type> -> categoria: ESPLICITA (TYPE_CATEGORY), cross-checkata
sui path dei <Ref> del dataset reale (ricognizione 2026-08-08:
traits/combat-traits -> 0, traits/faith-traits -> 1, traits/magic-traits ->
2, traits/social-traits -> 3, traits/campaign-traits -> 4,
traits/equipment-traits -> 5, voci "(faction)"/PFS -> 6, traits/race-traits
-> 7, traits/regional-traits -> 8, traits/religion-traits -> 9,
traits/drawbacks -> 10, Traits.aspx?Type=Exemplar -> 11). Un codice fuori
mappa e' un ERRORE dichiarato (ValueError), mai una categoria indovinata.

Note di formato:
- Nomi con entita' XML (es. "Fate&#8217;s Favored") decodificati da ET.
- 2 nomi duplicati nel dataset reale (Spidery Climber, Triaxian
  Dragonslayer): entrambe le voci restano (mai merge silenzioso) e i nomi
  sono elencati in counts.duplicateNames.
- <rReligion> e <Source> non servono al perimetro nome+categoria: non
  esportati.

Uso:
  python tools/import_pathbuilder_traits.py                 # scrive il JSON
  python tools/import_pathbuilder_traits.py --report-only   # solo stdout
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

# Mappa codice <Type> -> categoria. ESPLICITA, cross-check Ref (docstring).
TYPE_CATEGORY: dict[int, str] = {
    0: "Combat",
    1: "Faith",
    2: "Magic",
    3: "Social",
    4: "Campaign",
    5: "Equipment",
    6: "Faction",
    7: "Race",
    8: "Regional",
    9: "Religion",
    10: "Drawback",
    11: "Exemplar",
}


def parse_traits_xml(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Ritorna (entries, duplicateNames): [{name, category}], nomi duplicati."""
    root = ET.fromstring(text)
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in root.findall("Row"):
        name_el = row.findtext("Name")
        type_el = row.findtext("Type")
        if name_el is None or type_el is None:
            raise ValueError(
                "riga senza <Name> o <Type>: dato inatteso, " "mai scartato in silenzio"
            )
        name = name_el.strip()
        code = int(type_el)
        if code not in TYPE_CATEGORY:
            raise ValueError(
                f"<Type>{code}</Type> fuori mappa per {name!r}: "
                "categoria MAI indovinata"
            )
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
        entries.append({"name": name, "category": TYPE_CATEGORY[code]})
    return entries, duplicates


def build_document(raw_dir: Path) -> dict:
    path = raw_dir / "data_background_traits.xml"
    entries, duplicates = parse_traits_xml(path.read_text(encoding="utf-8"))
    per_category: dict[str, int] = {}
    for e in entries:
        per_category[e["category"]] = per_category.get(e["category"], 0) + 1
    return {
        "_provenance": {
            "source": "Pathbuilder 1e app data (data_background_traits.xml), "
            "estratto res/raw APK — dataset PI local-only, MAI committato",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_traits.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Solo nomi + categorie (fatti, non testo). MAI esportate "
            "<Description> (testo Paizo PI) ne' <Ref>.",
            "type_map": {str(k): v for k, v in sorted(TYPE_CATEGORY.items())},
        },
        "counts": {
            "entries": len(entries),
            "uniqueNames": len({e["name"] for e in entries}),
            "duplicateNames": sorted(duplicates),
            "perCategory": dict(sorted(per_category.items())),
        },
        "entries": entries,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    doc = build_document(Path(args.raw_dir))
    counts = doc["counts"]
    print(
        f"entries: {counts['entries']} (nomi unici {counts['uniqueNames']}, "
        f"duplicati {counts['duplicateNames']})"
    )
    for cat, n in counts["perCategory"].items():
        print(f"  {cat}: {n}")
    if args.report_only:
        return 0
    out = Path(args.out_dir) / "pathbuilder-background-traits.json"
    out.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"scritto {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
