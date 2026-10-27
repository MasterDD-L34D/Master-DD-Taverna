#!/usr/bin/env python3
"""Oracolo a tre vie (rilancio 2026-07-25): v1 | v2 | builder Taverna.

Legge `pathmaster-dd/data/reference/oracle-three-way.json` (dump
tools/oracle-three-way.mjs: input draft + derivati v1/v2), costruisce ogni
build col builder deterministico `src/pc` e confronta hp/bab/init/TS/
caratteristiche finali/conteggio talenti tra i TRE motori.

Normalizzazione nomi corpus (caveat noto): lowercase/strip separatori
("Half Orc" -> Half-Orc, "Halfelf" -> Half-Elf, "arcanist" -> Arcanist).
Razze flessibili (mods {"any": 2}): la scelta del bonus e' derivata
deterministicamente provando le 6 caratteristiche e tenendo quella che
riproduce le statistiche finali dello sheet.

Uso: .venv/Scripts/python tools/oracle_three_way.py [--check | --write]

Default (nessun flag): read-only, stampa il report su stdout senza
scrivere nulla. `--write` rigenera report + registry difetti.
`--check` (gate): read-only, exit 1 se il registry su disco non
coincide con quello ricalcolato dal dump corrente (drift).
Test: tests/test_oracle_three_way.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DUMP_PATH = (
    ROOT.parent / "pathmaster-dd" / "data" / "reference" / "oracle-three-way.json"
)
REPORT_PATH = ROOT / "reports" / "oracle_three_way.md"
DEFECTS_PATH = ROOT / "src" / "data" / "builds" / "_oracle_defects.json"

# Mappa esito oracolo -> classe di difetto del corpus GPT-A (decisione
# controller 2026-07-25: flag esplicito + sottoinsieme legale per i test;
# ricostruzione onesta del corpus come lotto futuro).
_DEFECT_CLASSES = {
    "FUORI_BUDGET_GPT": "stats_oltre_point_buy",
    "FEAT_ILLEGALE_GPT": "feat_count_oltre_raw",
    "PREREQ_ILLEGALE_GPT": "prerequisito_non_soddisfatto",
    "FLEX_INDETERMINATO": "bonus_razziale_mancante",
}

_ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]
_STAT_KEYS = {
    "FOR": "str",
    "DES": "dex",
    "COS": "con",
    "INT": "int",
    "SAG": "wis",
    "CAR": "cha",
}


def _norm_name(name: str) -> str:
    """Chiave normalizzata per il match ('Half Orc'/'halfelf' -> stessa chiave)."""
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


def _canon(catalog_path: Path, name: str) -> str | None:
    """Nome canonico del catalogo per la query (matching normalizzato)."""
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    for e in data["entries"]:
        if _norm_name(e["name"]) == _norm_name(name):
            return e["name"]
    return None


def _race_mods(race_name: str) -> tuple[str | None, dict]:
    races_path = ROOT / "data" / "reference" / "ogl" / "races.json"
    canon = _canon(races_path, race_name)
    if not canon:
        return None, {}
    races = json.loads(races_path.read_text(encoding="utf-8"))
    entry = next(e for e in races["entries"] if e["name"] == canon)
    return canon, entry.get("mechanics", {}).get("ability_mods") or {}


def _sheet_scores(sheet: dict | None) -> dict[str, int] | None:
    if not sheet:
        return None
    out = {}
    for k, v in sheet.items():
        if k in _STAT_KEYS and isinstance(v, int):
            out[_STAT_KEYS[k]] = v
    return out or None


def _flex_choice(draft_abilities: dict, mods: dict, sheet_scores: dict) -> str | None:
    """Razza flessibile: la caratteristica (di 6) che riproduce lo sheet."""
    if not sheet_scores:
        return None
    for ability in _ABILITIES:
        final = {
            a: draft_abilities.get(a, 10) + (2 if a == ability else 0)
            for a in _ABILITIES
        }
        if all(final[a] == sheet_scores.get(a) for a in _ABILITIES):
            return ability
    return None


def _compare(sheet: dict, v: dict | None, label: str, diffs: list):
    if not v:
        return  # motore assente per questa build: non e' divergenza
    for key in ("hp", "bab", "initiative"):
        if v.get(key) is None:
            continue  # campo non calcolato dal motore (v1: initiative): non e' divergenza
        if sheet.get(key) != v.get(key):
            diffs.append(f"{label} {key}: taverna {sheet.get(key)} vs {v.get(key)}")
    saves = sheet.get("saves") or {}
    for key in ("fort", "ref", "will"):
        if v.get(key) is None:
            continue
        if saves.get(key) != v.get(key):
            diffs.append(f"{label} {key}: taverna {saves.get(key)} vs {v.get(key)}")
    tab_ab = sheet.get("abilities") or {}
    v_ab = v.get("abilities") or {}
    for a in _ABILITIES:
        if a in v_ab and tab_ab.get(a) != v_ab[a]:
            diffs.append(f"{label} {a}: taverna {tab_ab.get(a)} vs {v_ab[a]}")


def _render_report(rows: list) -> str:
    """Testo del report Markdown (deterministico: niente date bruciate)."""
    n_concordant = sum(1 for r in rows if r["status"] == "CONCORDE")
    lines = [
        "# Oracolo a tre vie (v1 | v2 | builder Taverna)",
        "",
        "Rigenerato da `tools/oracle_three_way.py --write` sul dump "
        "`pathmaster-dd/data/reference/oracle-three-way.json`.",
        "",
        f"Build base: {len(rows)}. Concorde a tre: {n_concordant}. "
        f"Divergenze: {sum(1 for r in rows if r['status'] == 'DIVERGE')}. "
        f"Errori: {sum(1 for r in rows if r['status'] != 'CONCORDE' and r['status'] != 'DIVERGE')}.",
        "",
        "| Build | Esito | Divergenze |",
        "|---|---|---|",
    ]
    for r in rows:
        diffs = "; ".join(r["diffs"]) if r["diffs"] else "—"
        lines.append(f"| {r['file'].replace('.json', '')} | {r['status']} | {diffs} |")
    return "\n".join(lines) + "\n"


def _defects_payload(rows: list) -> dict:
    """Registry difetti corpus (flag gpt_defect): generato deterministicamente
    dall'oracolo. I test dei motori filtrano su questo file (build sane =
    non presenti nel registry)."""
    defects = {}
    for r in rows:
        classes = []
        if r["status"] in _DEFECT_CLASSES:
            classes.append(_DEFECT_CLASSES[r["status"]])
        if "prerequisito non soddisfatto" in " ".join(r["diffs"]):
            classes.append("prerequisito_non_soddisfatto")
        if classes:
            defects[r["file"]] = {
                "classes": sorted(set(classes)),
                "diffs": r["diffs"][:3],
            }
    return {
        "_comment": (
            "Flag difetti corpus GPT-A (decisione C 2026-07-25; lotto A "
            "rebuild 2026-07-27): rigenerato da tools/oracle_three_way.py "
            "--write. Le build NON presenti qui sono il sottoinsieme "
            "legale per i test dei motori. Le build ricostruite dal "
            "lotto A (tools/rebuild_corpus_gpt_a.py) portano il blocco "
            "di provenance sheet_payload.rebuild_gpt_a."
        ),
        "defects": defects,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="rigenera report e registry difetti su disco",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="read-only: exit 1 se il registry su disco e' "
        "in drift rispetto al ricalcolo dal dump",
    )
    args = ap.parse_args(argv)

    from src.pc.engine import build_character
    from src.pc.models import CharacterDraft

    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    rows = []
    COST = {
        7: -4,
        8: -2,
        9: -1,
        10: 0,
        11: 1,
        12: 2,
        13: 3,
        14: 5,
        15: 7,
        16: 10,
        17: 13,
        18: 17,
    }
    BUDGETS = [
        (10, "Low Fantasy"),
        (15, "Standard Fantasy"),
        (20, "High Fantasy"),
        (25, "Epic Fantasy"),
    ]
    for rec in dump:
        if rec.get("error"):
            rows.append(
                {"file": rec["file"], "status": "ERROR", "diffs": [rec["error"]]}
            )
            continue
        d = rec["draft"]
        race_canon, mods = _race_mods(d["race"])
        abilities = d.get("baseAbilities") or {}
        cost = sum(COST.get(v, 99) for v in abilities.values())
        budget = next((name for pts, name in BUDGETS if cost <= pts), None)
        if budget is None:
            # Finding oracolo: stats oltre Epic Fantasy 25 (GPT-A fuori RAW)
            rows.append(
                {
                    "file": rec["file"],
                    "status": "FUORI_BUDGET_GPT",
                    "diffs": [
                        f"point-buy {cost} > 25 (Epic Fantasy): stats illegali nel corpus"
                    ],
                }
            )
            continue
        race_bonus = None
        declared = d.get("flexDeclared")
        if mods.get("any") and declared:
            # Contratto E6-A6 (lotto A rebuild corpus): la build dichiara
            # sheet_payload.bonus_razziale_flessibile — la scelta non si
            # indovina piu' dallo sheet, si legge la dichiarazione.
            race_bonus = _STAT_KEYS.get(str(declared).upper())
            if race_bonus is None:
                rows.append(
                    {
                        "file": rec["file"],
                        "status": "TAVERNA_ERR",
                        "diffs": [f"bonus_razziale_flessibile non valido: {declared}"],
                    }
                )
                continue
        elif mods.get("any") and abilities:
            race_bonus = _flex_choice(
                abilities, mods, _sheet_scores(d.get("sheetAbilities"))
            )
        class_canon = _canon(
            ROOT / "data" / "reference" / "ogl" / "classes.json", d["class"]
        )
        draft = {
            "name": d["name"],
            "method": "point-buy",
            "campaign_type": budget,
            "abilities": abilities,
            "race": race_canon or d["race"],
            "class": class_canon or d["class"],
            "feats": d.get("feats") or [],
        }
        if race_bonus:
            draft["race_bonus_ability"] = race_bonus
        try:
            sheet = build_character(CharacterDraft.from_dict(draft))
        except Exception as exc:
            rows.append(
                {
                    "file": rec["file"],
                    "status": "TAVERNA_ERR",
                    "diffs": [str(exc)[:120]],
                }
            )
            continue
        if sheet.get("errors"):
            errs = sheet["errors"]
            first = errs[0]
            if "selezionati su" in first and "consentiti" in first:
                # Il builder e' l'unico motore che applica il limite RAW di
                # talenti: errore del CORPUS (classe di difetto gia' trovata
                # dallo spike 2026-07-19, adottata come warning in v1/v2).
                rows.append(
                    {
                        "file": rec["file"],
                        "status": "FEAT_ILLEGALE_GPT",
                        "diffs": errs[:2],
                    }
                )
            elif "race_bonus_ability obbligatorio" in first:
                rows.append(
                    {
                        "file": rec["file"],
                        "status": "FLEX_INDETERMINATO",
                        "diffs": [f"sheet GPT incoerente con ogni scelta +2: {first}"],
                    }
                )
            elif "prerequisito non soddisfatto" in " ".join(errs):
                # Prerequisito talento non soddisfatto (es. Arma accurata con
                # BAB 0 su rogue lv1): difetto del corpus, classe FEAT_ILLEGALE
                # in variante prerequisito (investigazione A3 2026-07-25).
                rows.append(
                    {
                        "file": rec["file"],
                        "status": "PREREQ_ILLEGALE_GPT",
                        "diffs": errs[:2],
                    }
                )
            else:
                rows.append(
                    {"file": rec["file"], "status": "TAVERNA_ERR", "diffs": errs[:2]}
                )
            continue
        diffs: list[str] = []
        _compare(sheet, rec.get("v1"), "v1", diffs)
        _compare(sheet, rec.get("v2"), "v2", diffs)
        status = "CONCORDE" if not diffs else "DIVERGE"
        rows.append(
            {
                "file": rec["file"],
                "status": status,
                "diffs": diffs,
                "race_bonus": race_bonus,
                "budget": budget,
            }
        )

    text = _render_report(rows)
    print(text[:3000])
    if args.check:
        payload = _defects_payload(rows)
        current = (
            json.loads(DEFECTS_PATH.read_text(encoding="utf-8"))
            if DEFECTS_PATH.exists()
            else None
        )
        if current == payload:
            print(
                f"CHECK OK: registry difetti allineato "
                f"({len(payload['defects'])} build flaggate)."
            )
            return 0
        print(
            "CHECK FALLITO: registry difetti in drift rispetto al dump "
            "corrente — rilanciare con --write e investigare il delta."
        )
        return 1
    if args.write:
        REPORT_PATH.write_text(text, encoding="utf-8")
        payload = _defects_payload(rows)
        DEFECTS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Report: {REPORT_PATH}")
        print(
            f"Registry difetti: {DEFECTS_PATH} ({len(payload['defects'])} build flaggate)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
