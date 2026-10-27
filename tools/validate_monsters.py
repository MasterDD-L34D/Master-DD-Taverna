#!/usr/bin/env python3
"""Validazione report-only dei mostri locali contro le medie per CR.

Confronta hp/ac/attacco/danno/TS di ogni mostro con il benchmark per CR
(valori meccanici della tabella di creazione mostri del Bestiary, non testo
espressivo) con tolleranza ±20%. Scrive un report markdown in
reports/monsters_cr_band.md (gitignored: NON committato).

Nessuna correzione automatica: exit code sempre 0.

Uso:
    .venv/Scripts/python tools/validate_monsters.py
    .venv/Scripts/python tools/validate_monsters.py \
        --source ../../sessione-2026-07-16/ricerca/PathfinderMonsterDatabase/data/full/data.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "reference" / "pi_local_only" / "monsters_local.json"
)
DEFAULT_REPORT = REPO_ROOT / "reports" / "monsters_cr_band.md"
DEFAULT_SOURCE = (
    REPO_ROOT.parent.parent
    / "sessione-2026-07-16"
    / "ricerca"
    / "PathfinderMonsterDatabase"
    / "data"
    / "full"
    / "data.json"
)

# Benchmark per CR (valori meccanici, scala di creazione mostri del gioco):
# CR -> (hp, ac, atk_high, atk_low, dmg_high, dmg_low, save_good, save_poor)
BENCHMARK = {
    0.5: (10, 11, 1, 0, 4, 3, 3, 0),
    1: (15, 12, 2, 1, 7, 5, 4, 1),
    2: (20, 14, 4, 3, 10, 7, 5, 1),
    3: (30, 15, 6, 4, 13, 9, 6, 2),
    4: (40, 17, 8, 6, 16, 12, 7, 3),
    5: (55, 18, 10, 7, 20, 15, 8, 4),
    6: (70, 19, 12, 8, 25, 18, 9, 5),
    7: (85, 20, 13, 10, 30, 22, 10, 6),
    8: (100, 21, 15, 11, 35, 26, 11, 7),
    9: (115, 23, 17, 12, 40, 30, 12, 8),
    10: (130, 24, 18, 13, 45, 33, 13, 9),
    11: (145, 25, 19, 14, 50, 37, 14, 10),
    12: (160, 27, 21, 15, 55, 41, 15, 11),
    13: (180, 28, 22, 16, 60, 45, 16, 12),
    14: (200, 29, 23, 17, 65, 48, 17, 12),
    15: (220, 30, 24, 18, 70, 52, 18, 13),
    16: (240, 31, 26, 19, 80, 60, 19, 14),
    17: (270, 32, 27, 20, 90, 67, 20, 15),
    18: (300, 33, 28, 21, 100, 75, 20, 16),
    19: (330, 34, 29, 22, 110, 82, 21, 16),
    20: (370, 36, 30, 23, 120, 90, 22, 17),
}
TOLERANCE = 0.20

_DICE_RE = re.compile(r"(\d+)d(\d+)\s*([+-]\s*\d+)?")


def avg_damage(expr: str) -> float:
    """Media di una espressione dadi tipo '2d6+5' (0.0 se non parsabile)."""
    m = _DICE_RE.search(expr or "")
    if not m:
        return 0.0
    num, die = int(m.group(1)), int(m.group(2))
    bonus = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    return num * (die + 1) / 2 + bonus


def _as_number(value, default=None):
    """Coercizione difensiva (dataset espanso: count/bonus eterogenei)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def max_attack_bonus(attacks: dict) -> int | None:
    """Massimo bonus di attacco tra le entry melee/ranged."""
    best = None
    for kind, groups in (attacks or {}).items():
        if kind == "special":
            continue
        for group in groups:
            for entry in group:
                for b in entry.get("bonus") or []:
                    b = _as_number(b)
                    if b is None:
                        continue
                    if best is None or b > best:
                        best = b
    return best


def max_group_damage(attacks: dict) -> float:
    """Massimo danno medio di un attacco completo (gruppo), con count."""
    best = 0.0
    for kind, groups in (attacks or {}).items():
        if kind == "special":
            continue
        for group in groups:
            total = 0.0
            for entry in group:
                count = _as_number(entry.get("count", 1), default=1) or 1
                per_hit = sum(
                    avg_damage(sub["damage"])
                    for part in entry.get("entries") or []
                    for sub in part
                    if "damage" in sub
                )
                total += count * per_hit
            best = max(best, total)
    return best


def _check(
    findings: list,
    name: str,
    cr: float,
    field: str,
    value: float | int | None,
    lo: float,
    hi: float,
) -> None:
    if value is None:
        return
    if value < lo or value > hi:
        findings.append(
            {
                "name": name,
                "cr": cr,
                "field": field,
                "value": value,
                "note": f"fuori banda [{lo:.1f}, {hi:.1f}]",
            }
        )


def validate(
    entries: list, legacy_35: set[str] | None = None, tolerance: float = TOLERANCE
) -> list[dict]:
    """Ritorna la lista dei rilievi (vuota = tutto in banda)."""
    findings: list[dict] = []
    for e in entries:
        name = e.get("name", "?")
        mech = e.get("mechanics") or {}
        cr = mech.get("cr")
        if legacy_35 and name in legacy_35:
            findings.append(
                {
                    "name": name,
                    "cr": cr,
                    "field": "legacy",
                    "value": True,
                    "note": "statblock 3.5 legacy (is_3.5)",
                }
            )
        if not isinstance(cr, (int, float)) or cr not in BENCHMARK:
            findings.append(
                {
                    "name": name,
                    "cr": cr,
                    "field": "cr",
                    "value": cr,
                    "note": "fuori range benchmark (0.5-20)",
                }
            )
            continue
        hp_b, ac_b, atk_hi, atk_lo, dmg_hi, dmg_lo, sv_g, sv_p = BENCHMARK[cr]
        t = tolerance
        _check(findings, name, cr, "hp", mech.get("hp"), hp_b * (1 - t), hp_b * (1 + t))
        _check(findings, name, cr, "ac", mech.get("ac"), ac_b * (1 - t), ac_b * (1 + t))
        _check(
            findings,
            name,
            cr,
            "attack",
            max_attack_bonus(mech.get("attacks")),
            atk_lo * (1 - t),
            atk_hi * (1 + t),
        )
        _check(
            findings,
            name,
            cr,
            "damage",
            max_group_damage(mech.get("attacks")),
            dmg_lo * (1 - t),
            dmg_hi * (1 + t),
        )
        saves = mech.get("saves") or {}
        for key in ("fort", "ref", "will"):
            _check(
                findings,
                name,
                cr,
                f"save_{key}",
                saves.get(key),
                sv_p * (1 - t),
                sv_g * (1 + t),
            )
    return findings


def _load_legacy_35(source_path: Path | None) -> set[str]:
    """Nomi dei mostri con is_3.5 nella fonte (se disponibile)."""
    if not source_path or not source_path.exists():
        return set()
    data = json.loads(source_path.read_text(encoding="utf-8"))
    return {m.get("title1", "") for m in data.values() if m.get("is_3.5")}


def main() -> None:
    ap = argparse.ArgumentParser(description="Validazione CR-band mostri (report-only)")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="data.json sorgente per flag 3.5 (opzionale)",
    )
    args = ap.parse_args()

    catalog = json.loads(args.input.read_text(encoding="utf-8"))
    entries = catalog.get("entries", [])
    findings = validate(entries, legacy_35=_load_legacy_35(args.source))

    lines = [
        "# Validazione CR-band mostri (report-only)",
        "",
        f"- Mostri validati: {len(entries)}",
        f"- Rilievi totali: {len(findings)}",
        f"- Tolleranza: ±{int(TOLERANCE * 100)}% sulle medie per CR",
        "",
        "| Mostro | CR | Campo | Valore | Nota |",
        "|---|---|---|---|---|",
    ]
    for f in findings:
        lines.append(
            f"| {f['name']} | {f['cr']} | {f['field']} | {f['value']} | {f['note']} |"
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Mostri: {len(entries)}, rilievi: {len(findings)}")
    print(f"Report (non committato): {args.report}")


if __name__ == "__main__":
    sys.exit(main())
