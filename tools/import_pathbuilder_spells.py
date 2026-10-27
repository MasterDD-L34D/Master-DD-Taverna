#!/usr/bin/env python3
"""Import del dataset Pathbuilder 1e "incantesimi" verso rules-engine-v2
(slice D5).

Parse di `data_spells.xml` in `data/reference/pi_local_only/pathbuilder/`
(estratto da res/raw dell'APK Pathbuilder 1e, BlueStacks dell'utente,
permesso concesso 2026-08-02 — dataset PI local-only, MAI committato) ed
emissione di UN JSON committato in `pathmaster-dd/packages/rules-engine-v2/
src/data/`: pathbuilder-spells.json — 2.922 incantesimi con nome, scuola,
sorgente e la MAPPA classe->livello parsata da <spellLevelsDisplay> (la
copertura PB per la riconciliazione a tre fonti, tools/build_spell_sources.py).

Disciplina OGL/PI identica a import_pathbuilder_equipment.py (D4): solo
nomi + meccaniche strutturate. MAI esportati <description> e <mythic>
(testo Paizo PI): restano nel dataset locale; del mythic resta solo il flag
booleano hasMythic.

Note di formato (ricognizione 2026-08-07, 2.922 righe):

- <spellLevelsDisplay> e' la dichiarazione AUTOREVOLE dei livelli per
  classe (e' cio' che l'app mostra). Forma regolare: segmenti "classe N"
  separati da virgola; la classe puo' essere COMBINATA ("cleric/oracle",
  "sorcerer/wizard", "summoner/unchained summoner") -> split su "/", OGNI
  classe della combinazione porta quel livello (stessa disciplina del loader
  Taverna su mechanics.spell_level).
- 4 segmenti su ~17.500 NON regolari (livello raddoppiato
  'summoner/unchained summoner 2 2' in Aquatic Cavalry/Fey Gate/Snowball;
  'inquisitor' senza livello in Deeper Darkness): preservati RAW in
  unparsedLevelSegments con il nome della spell, MAI parsati a tentativi.
- Alias di classe DICHIARATI (CLASS_ALIASES): 'magusUM' -> 'magus'
  (suffisso-libro UM residuo dello scrape d20pfsrd — lo stesso artefatto
  esiste nel dato Taverna, chiave 'magusum' in mechanics.spell_level di
  Storm Of Blades) e 'summoner (unchained)' -> 'unchained summoner' (PB usa
  entrambe le grafie nello stesso file, es. Absorbing Barrier vs Snowball).
- Le COLONNE per classe (<Wizard>3</Wizard>, ...) sono STALE per le spell
  dei manuali recenti e NON sono esportate: 223 classi in display senza
  colonna (es. arcanist/warpriest/hunter mai colonne), 5 livelli di colonna
  discordanti dal display (es. Absorbing Barrier: display summoner 4,
  colonna 2). Cross-check conteggiato in report.classColumnCrosscheck.
  NB: 'sorcerer' non ha MAI una colonna propria nel dato grezzo (condivide
  la lista wizard): non e' un mismatch, e' la forma del dato.
- <descriptor>: lista separata da virgole; 20 righe hanno un ';' di coda
  artefatto ("cold, water;") e una un ';' interno ("lawful; see text"):
  split su ',' e ';', token trimmati, vuoti scartati (regola meccanica
  dichiarata, nessuna interpretazione).
- <domain>/<bloodline>/<patron>: stringhe "Nome (livello), ..." esportate
  GREZZE (non parsate: copertura fuori dalla riconciliazione per classe,
  dichiarato).
- Nessun nome duplicato nel file (2.922 righe -> 2.922 nomi, verificato).

Uso:
  python tools/import_pathbuilder_spells.py                 # scrive il JSON
  python tools/import_pathbuilder_spells.py --report-only   # solo stdout
  --raw-dir PATH   (default data/reference/pi_local_only/pathbuilder)
  --out-dir PATH   (default <pathmaster sibling>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data/reference/pi_local_only/pathbuilder"
DEFAULT_OUT_DIR = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)

# Alias di classe DICHIARATI (artefatti del dato grezzo, non interpretazioni):
# - 'magusUM': suffisso-libro UM (Ultimate Magic) residuo dello scrape
#   d20pfsrd — presente in PB ('magusUM 2', Storm of Blades) e nel dato
#   Taverna ('magusum' in mechanics.spell_level). E' il MAGUS, non una
#   classe a parte.
# - 'summoner (unchained)': seconda grafia PB per l'unchained summoner
#   (l'altra e' 'unchained summoner' dentro la combinata
#   'summoner/unchained summoner'): stessa classe.
CLASS_ALIASES = {
    "magusum": "magus",
    "summoner (unchained)": "unchained summoner",
}

# Segmento regolare: "classe N" — la parte classe NON finisce in cifra
# (se finisce in cifra, come 'summoner/unchained summoner 2 2', il segmento
# e' irregolare e resta raw).
_SEGMENT_RE = re.compile(r"^(.*\D) (\d+)$")


def _class_id(raw: str) -> str:
    cid = " ".join(raw.strip().casefold().split())
    return CLASS_ALIASES.get(cid, cid)


def parse_spell_levels(display: str) -> tuple[dict[str, int], list[str]]:
    """(mappa classe->livello, segmenti irregolari preservati raw).

    Le classi combinate ("cleric/oracle") si splittano: ogni classe porta il
    livello del segmento. Segmenti non nella forma regolare "classe N":
    MAI parsati a tentativi, restituiti raw in coda.
    """
    levels: dict[str, int] = {}
    unparsed: list[str] = []
    for segment in display.split(","):
        segment = segment.strip()
        if not segment:
            continue
        match = _SEGMENT_RE.match(segment)
        if not match:
            unparsed.append(segment)
            continue
        for cls in match.group(1).split("/"):
            cid = _class_id(cls)
            # prima occorrenza vince (record, non pool — come il loader Taverna)
            if cid and cid not in levels:
                levels[cid] = int(match.group(2))
    return levels, unparsed


def _text(row: ET.Element, field: str) -> str | None:
    text = row.findtext(field)
    if text is None or not text.strip():
        return None
    return text.strip()


def _descriptors(row: ET.Element) -> list[str]:
    raw = _text(row, "descriptor")
    if not raw:
        return []
    # split su ',' e ';' (il ';' di coda e' un artefatto di 20 righe):
    # regola meccanica dichiarata, token vuoti scartati
    return [t for t in (p.strip() for p in re.split(r"[,;]", raw)) if t]


def import_spells(raw_dir: Path) -> list[dict]:
    out = []
    for row in ET.parse(raw_dir / "data_spells.xml").getroot().findall("Row"):
        levels, unparsed = parse_spell_levels(row.findtext("spellLevelsDisplay") or "")
        entry = {
            "name": (row.findtext("name") or "").strip(),
            "source": _text(row, "source"),
            "school": _text(row, "school"),
            "subschool": _text(row, "subschool"),
            "descriptors": _descriptors(row),
            "spellLevels": levels,
            # La stringa originale resta: trasparenza sul parsing
            "spellLevelsDisplay": (row.findtext("spellLevelsDisplay") or "").strip(),
            **({"unparsedLevelSegments": unparsed} if unparsed else {}),
            "castingTime": _text(row, "castingTime"),
            "components": _text(row, "components"),
            "range": _text(row, "range"),
            "targets": _text(row, "targets"),
            "area": _text(row, "area"),
            "effect": _text(row, "effect"),
            "duration": _text(row, "duration"),
            "savingThrow": _text(row, "savingThrow"),
            "spellResistance": _text(row, "sr"),
            # domain/bloodline/patron: "Nome (livello), ..." GREZZE
            # (copertura non di classe, dichiarata non parsata)
            "domains": _text(row, "domain"),
            "bloodlines": _text(row, "bloodline"),
            "patrons": _text(row, "patron"),
            # il testo mythic e' PI: resta solo il flag
            "hasMythic": _text(row, "mythic") is not None,
            # MAI: description (PI), mythic testo (PI), colonne per classe
            # (stale — cross-check nel report)
        }
        out.append(entry)
    return out


def _column_crosscheck(raw_dir: Path, spells: list[dict]) -> dict:
    """Cross-check colonne per classe (STALE) vs spellLevelsDisplay.

    Le colonne NON sono esportate (il display e' la dichiarazione autorevole);
    qui si conteggiano solo le discordanze, dichiarate. 'sorcerer' non ha mai
    colonna propria (condivide la lista wizard): non conteggiato.
    """
    rows = ET.parse(raw_dir / "data_spells.xml").getroot().findall("Row")
    mismatches = []
    display_without_column = 0
    for row, spell in zip(rows, spells):
        columns: dict[str, int] = {}
        for child in row:
            text = (child.text or "").strip()
            if child.tag[:1].isupper() and text.isdigit():
                columns[_class_id(child.tag.replace("_", " "))] = int(text)
        for cid, level in columns.items():
            if cid in spell["spellLevels"] and spell["spellLevels"][cid] != level:
                mismatches.append(
                    {
                        "spell": spell["name"],
                        "class": cid,
                        "displayLevel": spell["spellLevels"][cid],
                        "columnLevel": level,
                    }
                )
        for cid in spell["spellLevels"]:
            if cid not in columns and cid != "sorcerer":
                display_without_column += 1
    return {
        "columnLevelMismatches": len(mismatches),
        "mismatches": mismatches,
        "displayClassesWithoutColumn": display_without_column,
        "note": "Le colonne per classe del dataset PB sono STALE per le "
        "spell dei manuali recenti (223 classi in display senza "
        "colonna; 5 livelli di colonna discordanti). NON esportate: "
        "spellLevelsDisplay e' la dichiarazione autorevole. "
        "'sorcerer' non ha mai colonna propria nel dato grezzo "
        "(condivide la lista wizard): non conteggiato.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    spells = import_spells(raw_dir)
    name_counts = Counter(s["name"] for s in spells)
    duplicates = sorted(n for n, c in name_counts.items() if c > 1)
    unparsed = [
        {"spell": s["name"], "segment": seg}
        for s in spells
        for seg in s.get("unparsedLevelSegments", [])
    ]
    crosscheck = _column_crosscheck(raw_dir, spells)

    payload = {
        "_provenance": {
            "source": "Pathbuilder 1e raw data (res/raw dell'APK), data_spells.xml",
            "generated_by": "Master-DD-Taverna/tools/import_pathbuilder_spells.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Pathbuilder 1e raw data (APK da BlueStacks utente, permesso "
            "concesso 2026-08-02). Meccaniche e nomi: OGL 1.0a. Description "
            "e testo mythic: Product Identity — MAI esportati (restano "
            "nel dataset PI local-only, gitignored).",
            "desc_policy": "Solo nomi + meccaniche strutturate, MAI la <description> "
            "ne' il testo <mythic> (solo il flag hasMythic). "
            "domain/bloodline/patron esportati grezzi.",
            "levels_policy": "spellLevels e' parsato da <spellLevelsDisplay> "
            "(dichiarazione autorevole PB): segmenti 'classe N', "
            "classi combinate splittate su '/'. Segmenti non "
            "regolari preservati RAW in unparsedLevelSegments, "
            "MAI parsati a tentativi. Le colonne per classe "
            "(stale) NON sono esportate: cross-check nel report. "
            "Alias di classe DICHIARATI in report.classAliases.",
            "format_notes_doc": "tools/import_pathbuilder_spells.py (docstring)",
        },
        "counts": {
            "spells": len(spells),
            "duplicateNames": len(duplicates),
            "withUnparsedLevelSegments": len({u["spell"] for u in unparsed}),
            "unparsedLevelSegments": len(unparsed),
        },
        "report": {
            "duplicateNames": duplicates,
            "unparsedLevelSegments": unparsed,
            "classAliases": dict(CLASS_ALIASES),
            "classColumnCrosscheck": crosscheck,
        },
        "spells": spells,
    }

    print(
        f"incantesimi: {len(spells)} (nomi duplicati: {len(duplicates)}; "
        f"segmenti livello irregolari preservati raw: {len(unparsed)} su "
        f"{len({u['spell'] for u in unparsed})} spell)"
    )
    print(
        f"cross-check colonne: {crosscheck['columnLevelMismatches']} livelli "
        f"discordanti, {crosscheck['displayClassesWithoutColumn']} classi "
        f"display senza colonna (dichiarate)"
    )

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "pathbuilder-spells.json"
        path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
