#!/usr/bin/env python3
"""Import dei dataset Pathbuilder 1e "archetipi" verso rules-engine-v2 (slice D2).

Parse dei 42 XML `data_archetypes_*.xml` in
`data/reference/pi_local_only/pathbuilder/` (estratto da res/raw dell'APK
Pathbuilder 1e, BlueStacks dell'utente, permesso concesso 2026-08-02 —
dataset PI local-only, MAI committato) ed emissione di UN JSON committato in
`pathmaster-dd/packages/rules-engine-v2/src/data/`:

- pathbuilder-archetypes.json — i 1.361 archetipi (5.063 entries): per
  classe (nome file), per archetipo: source, race (archetipi razziali, dal
  campo <Race>) ed entries {special, level, replaced[], changed[],
  effectHook?}.

Disciplina OGL/PI identica a import_pathbuilder_races.py (D1): solo nomi +
meccaniche strutturate. MAI esportata la <Details> (testo Paizo, resta nel
dataset locale). Il catalogo curato `catalogs/archetypes.ts` (46 archetipi)
RESTA INTATTO e vince sempre sui duplicati: questo dataset e' additivo.

Note di formato (ricognizione 2026-08-07, 42 file / 5.069 righe / 1.361
archetipi):

- <ArchetypeName> compare SOLO sulla prima riga del blocco archetipo (con
  <Source>, <Details>, <Ref>); le righe seguenti ereditano l'archetipo
  corrente. Source e' quindi uniforme per archetipo per costruzione.
- <Replaced>/<Changed>: piu' voci separate da '&'; i suffissi progressivi
  ("Trap Sense +1&...&Trap Sense +6", "Weapon Training 1..4") restano PARTE
  DEL NOME — la progressione e' un dato onesto, non dedotta.
- <Completed>Yes</Completed> e' una sentinella di fine blocco: 6 righe hanno
  SOLO Completed (nessuno special/replaced/changed) e vengono saltate.
- 3 righe hanno <ArchetypeSpecial> senza <Level> (Clone Master "Bomb",
  Esoteric "Unarmed Strike", Contemplative "Know the Unseen Disciples"):
  level null dichiarato, mai inventato.
- <EffectMethod> e' il nome di un hook interno dell'app (camelCase), NON un
  effetto: esportato come `effectHook` dichiarato, mai decodificato.
- <Race> (100 archetipi razziali): una riga per archetipo; esportato come
  `race` a livello archetipo, null altrove.
- Classi PB fuori dal nostro corpus classi (unchained_rogue, omdura):
  importate comunque — sono dataset; la risoluzione motore le raggiunge solo
  se la classe esiste da noi (comportamento dichiarato in archetypes-pb.ts).

Uso:
  python tools/import_pathbuilder_archetypes.py                 # scrive il JSON
  python tools/import_pathbuilder_archetypes.py --report-only   # solo stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import glob
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

SEP_LIST = "&"


def parse_xml(text: str) -> ET.Element:
    return ET.fromstring(text)


def iter_rows(root: ET.Element) -> list[ET.Element]:
    return root.findall("Row")


def _split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    # Un solo caso reale nel dataset (paladin, Changed "Smite Evil&") ha un
    # separatore di coda: le parti vuote sono scartate, non voci fantasma.
    return [p.strip() for p in raw.split(SEP_LIST) if p.strip()]


def _class_key(path: Path) -> str:
    name = path.name
    assert name.startswith("data_archetypes_") and name.endswith(".xml")
    return name[len("data_archetypes_") : -len(".xml")]


def parse_archetype_file(path: Path) -> tuple[dict[str, dict], int]:
    """Blocchi per archetipo: ArchetypeName/Source solo sulla prima riga.

    Ritorna (archetipi, sentinelle Completed-only saltate)."""
    archetypes: dict[str, dict] = {}
    current: dict | None = None
    skipped = 0
    for row in iter_rows(ET.parse(path).getroot()):
        name = row.findtext("ArchetypeName")
        if name is not None:
            current = {"source": row.findtext("Source"), "race": None, "entries": []}
            archetypes[name.strip()] = current
        if current is None:
            raise ValueError(f"{path.name}: riga senza blocco archetipo aperto")
        if row.findtext("Race"):
            if (
                current["race"] is not None
                and current["race"] != row.findtext("Race").strip()
            ):
                raise ValueError(f"{path.name}: race non uniforme nel blocco")
            current["race"] = row.findtext("Race").strip()
        special = row.findtext("ArchetypeSpecial")
        replaced = _split_list(row.findtext("Replaced"))
        changed = _split_list(row.findtext("Changed"))
        if special is None and not replaced and not changed:
            # sentinella <Completed>Yes</Completed> di fine blocco
            skipped += 1
            continue
        level_text = row.findtext("Level")
        entry: dict = {
            "special": special.strip() if special else None,
            "level": int(level_text) if level_text else None,
            "replaced": replaced,
            "changed": changed,
        }
        hook = row.findtext("EffectMethod")
        if hook:
            entry["effectHook"] = hook.strip()
        current["entries"].append(entry)
    return archetypes, skipped


def import_archetypes(raw_dir: Path) -> dict[str, dict[str, dict]]:
    """Per classe (nome file): per archetipo: source/race/entries."""
    classes: dict[str, dict[str, dict]] = {}
    for path in sorted(glob.glob(str(raw_dir / "data_archetypes_*.xml"))):
        archs, _skipped = parse_archetype_file(Path(path))
        classes[_class_key(Path(path))] = archs
    return classes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    classes = import_archetypes(raw_dir)

    all_entries = [
        (cls, name, e)
        for cls, archs in classes.items()
        for name, arch in archs.items()
        for e in arch["entries"]
    ]
    without_level = [
        {"class": cls, "archetype": name, "special": e["special"]}
        for cls, name, e in all_entries
        if e["level"] is None
    ]
    # righe saltate = 5.069 righe totali meno le entries raccolte
    total_rows = sum(
        len(iter_rows(ET.parse(p).getroot()))
        for p in sorted(glob.glob(str(raw_dir / "data_archetypes_*.xml")))
    )
    skipped = total_rows - len(all_entries)

    payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), "
            "data_archetypes_*.xml (42 classi)",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_archetypes.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. <Details> "
            "degli archetipi: testo Paizo (Product Identity) — MAI esportato "
            "(resta nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo nomi + meccaniche strutturate (special, level, "
            "replaced[], changed[], source, race): MAI la <Details> "
            "delle voci. Il catalogo curato catalogs/archetypes.ts "
            "(46 archetipi) RESTA INTATTO e vince sempre sui duplicati: "
            "questo dataset e' additivo.",
            "effecthook_policy": "effectHook e' il nome dell'hook interno Pathbuilder "
            "(EffectMethod, camelCase): dichiarato come hook, NON "
            "decodificato e NON un effetto del motore.",
            "level_policy": "level SOLO dal dato; 3 entries senza <Level> nel dataset "
            "hanno level null dichiarato (report), mai inventato. I "
            "suffissi progressivi (+N, ' N') restano parte dei nomi "
            "replaced/changed: la progressione e' un dato onesto.",
            "format_notes_doc": "tools/import_pathbuilder_archetypes.py (docstring)",
        },
        "counts": {
            "classes": len(classes),
            "archetypes": sum(len(a) for a in classes.values()),
            "entries": len(all_entries),
            "entriesWithoutLevel": len(without_level),
        },
        "report": {
            "skippedCompletedSentinels": skipped,
            "entriesWithoutLevel": without_level,
        },
        "classes": classes,
    }

    print(
        f"classi: {len(classes)}, archetipi: {payload['counts']['archetypes']}, "
        f"entries: {len(all_entries)}"
    )
    print(f"entries senza level nel dato (dichiarate): {len(without_level)}")
    print(f"sentinelle Completed saltate: {skipped}")
    per_class = {c: len(a) for c, a in classes.items()}
    print("archetipi per classe:", per_class)

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "pathbuilder-archetypes.json"
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
