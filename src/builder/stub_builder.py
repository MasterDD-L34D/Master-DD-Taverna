"""Stub builder payload generation for the MinMax Builder module.

This module isolates the ~900-line stub-generation logic previously embedded
inside ``GET /modules/{name}``. It is consumed by ``src.app`` and by any
client that wants to produce a deterministic build stub without downloading
the full ``minmax_builder.txt`` text.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from jsonschema.exceptions import ValidationError

from tools.generate_build_db import schema_for_mode, validate_with_schema
from ..metadata_parser import load_reference_manifest as _load_reference_manifest


class StubBuilderError(Exception):
    """Raised when the stub builder cannot produce a valid payload."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_mode(mode: str | None, body: dict[str, Any] | None) -> str:
    """Resolve effective builder mode to ``core`` or ``extended``."""
    builder_mode = (body or {}).get("builder_mode") or (body or {}).get("mode") or mode
    return "core" if str(builder_mode or "").lower().startswith("core") else "extended"


def build_stub_payload(
    class_name: str | None,
    race: str | None,
    archetype: str | None,
    level: int | None,
    mode: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate a deterministic stub payload.

    Parameters
    ----------
    class_name:
        Character class (e.g. ``wizard``).
    race:
        Character race (default ``Human``).
    archetype:
        Class archetype (default ``Base``).
    level:
        Character level (default ``1``).
    mode:
        Query/default mode string; ``core`` starts with ``core``,
        everything else is treated as ``extended``.
    body:
        Optional JSON body for overrides (``race``, ``archetype``,
        ``level``, ``mode``, ``builder_mode``, ``hooks``).

    Returns
    -------
    dict[str, Any]
        The full payload including ``catalog_manifest`` and
        ``reference_catalog_version``. Callers that expose the payload to
        clients should strip those two keys.

    Raises
    ------
    StubBuilderError
        If required inputs are missing or validation fails.
    """
    resolved_race = race or (body or {}).get("race") or "Human"
    resolved_archetype = (
        archetype
        or (body or {}).get("archetype")
        or (body or {}).get("model")
        or "Base"
    )

    normalized_mode = _normalize_mode(mode, body)
    step_total = 8 if normalized_mode == "core" else 16
    resolved_level = int((body or {}).get("level") or level or 1)
    step_labels = {
        "1": "Profilo Base",
        "2": "Razza & Classe",
        "3": "Archetipi & Multiclasse",
        "4": "Feats & Talenti",
        "5": "Spell & Power Set",
        "6": "Equip & Risorse",
        "7": "Benchmark & Simulazioni",
        "8": "QA & Export",
    }
    if normalized_mode == "extended":
        step_labels.update(
            {
                "9": "Dummies Sheet",
                "10": "Esportazione",
                "11": "Fork/Varianti",
                "12": "Comparativa",
                "13": "Meta Rating",
                "14": "Companion",
                "15": "Report",
                "16": "Chiusura",
            }
        )

    base_build_state = {
        "class": class_name or "Unknown",
        "mode": normalized_mode,
        "race": resolved_race,
        "archetype": resolved_archetype,
        "step": 1,
        "step_total": step_total,
        "step_labels": step_labels,
    }

    benchmark = {
        "meta_tier": "T3",
        "ruling_badge": "validated",
        "dpr_snapshot": {
            "livello_1": {"media": 6, "picco": 9},
            "livello_5": {"media": 18, "picco": 26},
        },
    }

    is_wizard_evoker = (
        str(class_name or "").lower() == "wizard"
        and str(resolved_archetype or "").lower() == "evoker"
    )

    wizard_progression_plan: list[dict[str, object]] = [
        {
            "livello": 1,
            "talenti": ["Iniziativa migliorata"],
            "slot": "1°: 4",
            "equip": ["Bastone ferrato", "Spellbook", "Abito da viaggiatore"],
            "pf": 12,
            "salvezze": {"Tempra": 2, "Riflessi": 3, "Volontà": 4},
            "skills": {
                "Conoscenze (arcana)": 6,
                "Sapienza Magica": 6,
                "Percezione": 5,
            },
            "ca": {
                "totale": 15,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 0,
                "misc": 0,
            },
            "privilegi": [
                "Legame arcano (famiglio)",
                "Scuola di Invocazione — Intensified Spells",
                "PF 12 | TS +2/+3/+4 | CA 15",
                "Slot 1°:4 | Equip: bastone ferrato, spellbook, abito da viaggiatore",
            ],
        },
        {
            "livello": 2,
            "talenti": ["Metamagia (Incantesimi Estesi)"],
            "slot": "1°: 5 / 2°: 2",
            "equip": ["Pagina di pergamena", "Mantello resistente +1"],
            "pf": 20,
            "salvezze": {"Tempra": 3, "Riflessi": 4, "Volontà": 5},
            "skills": {
                "Conoscenze (arcana)": 7,
                "Sapienza Magica": 7,
                "Percezione": 6,
            },
            "ca": {
                "totale": 15,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 0,
                "misc": 0,
            },
            "privilegi": [
                "Potere di scuola (Evoker's Admixture)",
                "PF 20 | TS +3/+4/+5 | CA 15",
                "Slot 1°:5 / 2°:2 | Equip: pergamene aggiuntive, mantello resistente +1",
            ],
        },
        {
            "livello": 3,
            "talenti": ["Incantesimi focalizzati (Invocazione)"],
            "slot": "1°: 6 / 2°: 4 / 3°: 2",
            "equip": ["Bacchetta di dardo incantato (CL3)"],
            "pf": 28,
            "salvezze": {"Tempra": 3, "Riflessi": 4, "Volontà": 6},
            "skills": {
                "Conoscenze (arcana)": 9,
                "Sapienza Magica": 9,
                "Percezione": 6,
            },
            "ca": {
                "totale": 16,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 1,
                "misc": 0,
            },
            "privilegi": [
                "Talento bonus del mago",
                "PF 28 | TS +3/+4/+6 | CA 16",
                "Slot 1°:6 / 2°:4 / 3°:2 | Equip: bacchetta di dardo incantato (CL3)",
            ],
        },
        {
            "livello": 4,
            "talenti": ["Magia focalizzata superiore (Invocazione)"],
            "slot": "1°: 6 / 2°: 5 / 3°: 4",
            "equip": ["Veste da mago rinforzata"],
            "pf": 36,
            "salvezze": {"Tempra": 4, "Riflessi": 5, "Volontà": 7},
            "skills": {
                "Conoscenze (arcana)": 10,
                "Sapienza Magica": 10,
                "Percezione": 7,
            },
            "ca": {
                "totale": 16,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 1,
                "misc": 0,
            },
            "privilegi": [
                "Scoperta arcana: specializzazione intensificata",
                "PF 36 | TS +4/+5/+7 | CA 16",
                "Slot 1°:6 / 2°:5 / 3°:4 | Equip: veste da mago rinforzata",
            ],
        },
        {
            "livello": 5,
            "talenti": ["Incantesimi massimizzati (metamagia)"],
            "slot": "1°: 7 / 2°: 6 / 3°: 5 / 4°: 3",
            "equip": ["Perla di potere I", "Anello di protezione +1"],
            "pf": 44,
            "salvezze": {"Tempra": 4, "Riflessi": 5, "Volontà": 8},
            "skills": {
                "Conoscenze (arcana)": 12,
                "Sapienza Magica": 12,
                "Percezione": 8,
            },
            "ca": {
                "totale": 17,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 1,
                "misc": 1,
            },
            "privilegi": [
                "Scuola di opposizione consolidata",
                "PF 44 | TS +4/+5/+8 | CA 17",
                "Slot 1°:7 / 2°:6 / 3°:5 / 4°:3 | Equip: perla di potere I, anello di protezione +1",
            ],
        },
        {
            "livello": 6,
            "talenti": ["Talento bonus (Mago) — Incantesimi rapidi"],
            "slot": "1°: 7 / 2°: 6 / 3°: 6 / 4°: 4",
            "equip": ["Bacchetta di palla di fuoco (CL6)"],
            "pf": 52,
            "salvezze": {"Tempra": 5, "Riflessi": 6, "Volontà": 9},
            "skills": {
                "Conoscenze (arcana)": 13,
                "Sapienza Magica": 13,
                "Percezione": 9,
            },
            "ca": {
                "totale": 17,
                "armatura": 3,
                "destrezza": 2,
                "deflessione": 1,
                "misc": 1,
            },
            "privilegi": [
                "Potere di scuola avanzato (Force Missile)",
                "PF 52 | TS +5/+6/+9 | CA 17",
                "Slot 1°:7 / 2°:6 / 3°:6 / 4°:4 | Equip: bacchetta di palla di fuoco (CL6)",
            ],
        },
        {
            "livello": 7,
            "talenti": [
                "Incantesimi focalizzati superiori (Invocazione)",
                "Talento bonus (Difensivo)",
            ],
            "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 5 / 5°: 3",
            "equip": ["Cintura della destrezza +2"],
            "pf": 60,
            "salvezze": {"Tempra": 5, "Riflessi": 6, "Volontà": 10},
            "skills": {
                "Conoscenze (arcana)": 14,
                "Sapienza Magica": 14,
                "Percezione": 9,
            },
            "ca": {
                "totale": 18,
                "armatura": 3,
                "destrezza": 3,
                "deflessione": 1,
                "misc": 1,
            },
            "privilegi": [
                "Talento bonus del mago (difesa arcana)",
                "PF 60 | TS +5/+6/+10 | CA 18",
                "Slot 1°:8 / 2°:7 / 3°:7 / 4°:5 / 5°:3 | Equip: cintura della destrezza +2",
            ],
        },
        {
            "livello": 8,
            "talenti": ["Penetrare resistenza magica"],
            "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 6 / 5°: 4",
            "equip": ["Pergamena di muro di forza"],
            "pf": 68,
            "salvezze": {"Tempra": 6, "Riflessi": 7, "Volontà": 11},
            "skills": {
                "Conoscenze (arcana)": 15,
                "Sapienza Magica": 15,
                "Percezione": 10,
            },
            "ca": {
                "totale": 18,
                "armatura": 3,
                "destrezza": 3,
                "deflessione": 1,
                "misc": 1,
            },
            "privilegi": [
                "Ricerca superiore (arcane discovery)",
                "PF 68 | TS +6/+7/+11 | CA 18",
                "Slot 1°:8 / 2°:7 / 3°:7 / 4°:6 / 5°:4 | Equip: pergamena di muro di forza",
            ],
        },
        {
            "livello": 9,
            "talenti": ["Incantesimi rapidi migliorati"],
            "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 7 / 5°: 5",
            "equip": ["Bacchetta di fulmine (CL9)"],
            "pf": 76,
            "salvezze": {"Tempra": 6, "Riflessi": 7, "Volontà": 12},
            "skills": {
                "Conoscenze (arcana)": 17,
                "Sapienza Magica": 17,
                "Percezione": 10,
            },
            "ca": {
                "totale": 19,
                "armatura": 3,
                "destrezza": 3,
                "deflessione": 2,
                "misc": 1,
            },
            "privilegi": [
                "Talento bonus (metamagia di scuola)",
                "PF 76 | TS +6/+7/+12 | CA 19",
                "Slot 1°:8 / 2°:7 / 3°:7 / 4°:7 / 5°:5 | Equip: bacchetta di fulmine (CL9)",
            ],
        },
        {
            "livello": 10,
            "talenti": [
                "Incantesimi potenziati (metamagia)",
                "Penetrare resistenza magica migliorato",
            ],
            "slot": "1°: 8 / 2°: 7 / 3°: 7 / 4°: 7 / 5°: 6",
            "equip": ["Testa di bacco runica", "Perla di potere IV"],
            "pf": 84,
            "salvezze": {"Tempra": 7, "Riflessi": 8, "Volontà": 13},
            "skills": {
                "Conoscenze (arcana)": 18,
                "Sapienza Magica": 18,
                "Percezione": 11,
            },
            "ca": {
                "totale": 20,
                "armatura": 3,
                "destrezza": 3,
                "deflessione": 2,
                "misc": 2,
            },
            "privilegi": [
                "Potere di scuola maggiore (elemental mastery)",
                "PF 84 | TS +7/+8/+13 | CA 20",
                "Slot 1°:8 / 2°:7 / 3°:7 / 4°:7 / 5°:6 | Equip: perla di potere IV, focus arcani runici",
            ],
        },
    ]

    is_cutpurse = (
        str(class_name or "").lower() == "rogue"
        and str(resolved_archetype or "").lower() == "cutpurse"
    )

    cutpurse_progression_plan: list[dict[str, object]] = [
        {
            "livello": 1,
            "stats": {
                "FOR": 12,
                "DES": 18,
                "COS": 12,
                "INT": 14,
                "SAG": 10,
                "CAR": 8,
            },
            "talenti": ["Arma accurata"],
            "pf": 11,
            "attacco": "+6 (pugnale) / +5 (fionda)",
            "danni": "1d4+2 (pugnale) / 1d3+2 (fionda)",
            "salvezze": {"Tempra": 2, "Riflessi": 4, "Volontà": 1},
            "skills": {
                "Furtività": 9,
                "Rapidità di mano": 9,
                "Percezione": 6,
                "Acrobazia": 8,
                "Disattivare Congegni": 9,
            },
            "ca": {"totale": 18, "armatura": 3, "destrezza": 4, "misc": 1},
            "equip": [
                "Armatura di cuoio borchiato",
                "Pugnale bilanciato",
                "Fionda con 20 proiettili",
                "Attrezzi da scasso di qualità",
            ],
            "privilegi": [
                "Attacco furtivo +1d6",
                "Percepire trappole +1",
                "Cutpurse: Mano lesta (Pickpocket)",
                "PF 11 | TS +2/+4/+1 | CA 18",
            ],
        },
        {
            "livello": 2,
            "talenti": ["Schivare prodigioso"],
            "pf": 18,
            "attacco": "+7 (pugnale)",
            "danni": "1d4+2 (pugnale) +1d6 furtivo",
            "salvezze": {"Tempra": 3, "Riflessi": 5, "Volontà": 1},
            "skills": {
                "Furtività": 10,
                "Rapidità di mano": 10,
                "Percezione": 7,
                "Acrobazia": 9,
                "Disattivare Congegni": 10,
            },
            "ca": {"totale": 19, "armatura": 3, "destrezza": 4, "misc": 2},
            "equip": ["Cappa elfica grigia", "Mantello della resistenza +1"],
            "privilegi": [
                "Talento ladresco: Furtività rapida",
                "Cutpurse: Afferrare oggetti (Quick Steal)",
                "PF 18 | TS +3/+5/+1 | CA 19",
            ],
        },
        {
            "livello": 3,
            "talenti": ["Schivare"],
            "pf": 26,
            "attacco": "+8 (pugnale)",
            "danni": "1d4+3 (pugnale) +2d6 furtivo",
            "salvezze": {"Tempra": 3, "Riflessi": 6, "Volontà": 2},
            "skills": {
                "Furtività": 11,
                "Rapidità di mano": 11,
                "Percezione": 8,
                "Acrobazia": 10,
                "Intimidire": 5,
            },
            "ca": {
                "totale": 19,
                "armatura": 3,
                "destrezza": 4,
                "schivare": 1,
                "misc": 1,
            },
            "equip": ["Pugnale masterwork", "Anello di protezione +1"],
            "privilegi": [
                "Attacco furtivo +2d6",
                "Scherma agile (Finesse Training)",
                "PF 26 | TS +3/+6/+2 | CA 19",
            ],
        },
        {
            "livello": 4,
            "talenti": ["Arma focalizzata (pugnale)"],
            "pf": 34,
            "attacco": "+10 (pugnale)",
            "danni": "1d4+4 (pugnale) +2d6 furtivo",
            "salvezze": {"Tempra": 4, "Riflessi": 7, "Volontà": 2},
            "skills": {
                "Furtività": 12,
                "Rapidità di mano": 12,
                "Percezione": 9,
                "Acrobazia": 11,
                "Diplomazia": 5,
            },
            "ca": {
                "totale": 20,
                "armatura": 4,
                "destrezza": 4,
                "schivare": 1,
                "misc": 1,
            },
            "equip": ["Giaco di maglia ombreggiato", "Guanti da ladro"],
            "privilegi": [
                "Talento ladresco: Arma improvvisata",
                "Uncanny Dodge",
                "PF 34 | TS +4/+7/+2 | CA 20",
            ],
        },
        {
            "livello": 5,
            "talenti": ["Combattere con due armi"],
            "pf": 42,
            "attacco": "+11/+11 (pugnali)",
            "danni": "1d4+4 (pugnale) +3d6 furtivo",
            "salvezze": {"Tempra": 4, "Riflessi": 8, "Volontà": 3},
            "skills": {
                "Furtività": 13,
                "Rapidità di mano": 13,
                "Percezione": 10,
                "Acrobazia": 12,
                "Disattivare Congegni": 13,
            },
            "ca": {
                "totale": 21,
                "armatura": 4,
                "destrezza": 4,
                "schivare": 1,
                "misc": 2,
            },
            "equip": ["Pugnale +1", "Cintura dell'agilità +2"],
            "privilegi": [
                "Attacco furtivo +3d6",
                "Talento ladresco: Attacco debilitante",
                "PF 42 | TS +4/+8/+3 | CA 21",
            ],
        },
        {
            "livello": 6,
            "talenti": ["Riflessi in combattimento"],
            "pf": 50,
            "attacco": "+13/+13 (pugnali)",
            "danni": "1d4+5 (pugnale) +3d6 furtivo",
            "salvezze": {"Tempra": 5, "Riflessi": 9, "Volontà": 3},
            "skills": {
                "Furtività": 14,
                "Rapidità di mano": 14,
                "Percezione": 11,
                "Acrobazia": 13,
                "Raggirare": 9,
            },
            "ca": {
                "totale": 22,
                "armatura": 4,
                "destrezza": 5,
                "schivare": 1,
                "misc": 2,
            },
            "equip": ["Stivali dell'agilità", "Mantello della resistenza +2"],
            "privilegi": [
                "Talento ladresco: Furtività leggendaria",
                "Evasione migliorata",
                "PF 50 | TS +5/+9/+3 | CA 22",
            ],
        },
        {
            "livello": 7,
            "talenti": ["Mobilità"],
            "pf": 58,
            "attacco": "+15/+15 (pugnali)",
            "danni": "1d4+6 (pugnale) +4d6 furtivo",
            "salvezze": {"Tempra": 5, "Riflessi": 10, "Volontà": 4},
            "skills": {
                "Furtività": 15,
                "Rapidità di mano": 15,
                "Percezione": 12,
                "Acrobazia": 14,
                "Disattivare Congegni": 15,
            },
            "ca": {
                "totale": 23,
                "armatura": 5,
                "destrezza": 5,
                "schivare": 1,
                "misc": 2,
            },
            "equip": ["Pugnale +2 bilanciato", "Bracciali dell'armatura +1"],
            "privilegi": [
                "Attacco furtivo +4d6",
                "Cutpurse: Ruba arma (Steal Weapon)",
                "PF 58 | TS +5/+10/+4 | CA 23",
            ],
        },
        {
            "livello": 8,
            "stats": {
                "FOR": 12,
                "DES": 20,
                "COS": 12,
                "INT": 14,
                "SAG": 10,
                "CAR": 8,
            },
            "talenti": [
                "Arma focalizzata superiore (pugnale)",
                "Talento ladresco: Opportunista",
            ],
            "pf": 66,
            "attacco": "+17/+17 (pugnali)",
            "danni": "1d4+6 (pugnale) +4d6 furtivo",
            "salvezze": {"Tempra": 6, "Riflessi": 11, "Volontà": 4},
            "skills": {
                "Furtività": 17,
                "Rapidità di mano": 17,
                "Percezione": 13,
                "Acrobazia": 15,
                "Intuizione": 11,
            },
            "ca": {
                "totale": 24,
                "armatura": 5,
                "destrezza": 6,
                "schivare": 1,
                "misc": 2,
            },
            "equip": ["Cintura dell'agilità +4", "Pugnale agile +2"],
            "privilegi": [
                "Schivare prodigioso migliorato",
                "Attacco furtivo +4d6",
                "PF 66 | TS +6/+11/+4 | CA 24",
            ],
        },
        {
            "livello": 9,
            "talenti": ["Arma accurata superiore"],
            "pf": 74,
            "attacco": "+19/+19 (pugnali)",
            "danni": "1d4+7 (pugnale) +5d6 furtivo",
            "salvezze": {"Tempra": 6, "Riflessi": 12, "Volontà": 5},
            "skills": {
                "Furtività": 18,
                "Rapidità di mano": 18,
                "Percezione": 14,
                "Acrobazia": 16,
                "Diplomazia": 8,
            },
            "ca": {
                "totale": 25,
                "armatura": 5,
                "destrezza": 6,
                "schivare": 1,
                "misc": 3,
            },
            "equip": ["Pugnale velocità +2", "Anello di protezione +2"],
            "privilegi": [
                "Attacco furtivo +5d6",
                "Talento ladresco: Debilitare difese",
                "PF 74 | TS +6/+12/+5 | CA 25",
            ],
        },
        {
            "livello": 10,
            "talenti": ["Colpo senz'armi migliorato"],
            "pf": 82,
            "attacco": "+21/+21 (pugnali)",
            "danni": "1d4+8 (pugnale) +5d6 furtivo",
            "salvezze": {"Tempra": 7, "Riflessi": 13, "Volontà": 5},
            "skills": {
                "Furtività": 19,
                "Rapidità di mano": 19,
                "Percezione": 15,
                "Acrobazia": 17,
                "Disattivare Congegni": 19,
            },
            "ca": {
                "totale": 26,
                "armatura": 6,
                "destrezza": 6,
                "schivare": 1,
                "misc": 3,
            },
            "equip": [
                "Giaco di maglia ombreggiato +2",
                "Guanti della destrezza +4",
            ],
            "privilegi": [
                "Attacco furtivo +5d6",
                "Talento ladresco: Bleeding Attack",
                "Cutpurse: Maestro borseggiatore",
                "PF 82 | TS +7/+13/+5 | CA 26",
            ],
        },
    ]

    progression: list[dict[str, object]] = []
    base_hp = 12 + 5 * max(resolved_level - 1, 0)

    wizard_levels = (
        [
            entry
            for entry in wizard_progression_plan
            if entry["livello"] <= resolved_level
        ]
        if is_wizard_evoker
        else []
    )
    wizard_snapshot = wizard_levels[-1] if wizard_levels else None

    cutpurse_levels = (
        [
            entry
            for entry in cutpurse_progression_plan
            if entry["livello"] <= resolved_level
        ]
        if is_cutpurse
        else []
    )
    cutpurse_snapshot = cutpurse_levels[-1] if cutpurse_levels else None

    if is_wizard_evoker:
        for entry in wizard_levels:
            progression.append(
                {
                    "livello": entry["livello"],
                    "privilegi": entry["privilegi"],
                    "talenti": entry["talenti"],
                }
            )
        if progression:
            base_hp = (
                wizard_snapshot.get("pf", base_hp) if wizard_snapshot else base_hp
            )
    elif is_cutpurse:
        for entry in cutpurse_levels:
            progression.append(
                {
                    "livello": entry["livello"],
                    "privilegi": entry.get("privilegi", []),
                    "talenti": entry.get("talenti", []),
                }
            )
        if progression and cutpurse_snapshot:
            base_hp = cutpurse_snapshot.get("pf", base_hp)
    else:
        for lvl in range(1, resolved_level + 1):
            progression.append(
                {
                    "livello": lvl,
                    "privilegi": [
                        f"Privilegio {lvl}",
                        (
                            f"Tecnica distintiva {resolved_archetype}"
                            if resolved_archetype
                            else "Tecnica distintiva"
                        ),
                    ],
                    "talenti": [f"Talento di livello {lvl}"],
                }
            )

    hp_progression: list[object] = []
    if is_wizard_evoker:
        hp_progression = [entry.get("pf", base_hp) for entry in wizard_levels]
    elif is_cutpurse:
        hp_progression = [entry.get("pf", base_hp) for entry in cutpurse_levels]
    if not hp_progression:
        hp_progression = [base_hp]

    snapshot = wizard_snapshot or cutpurse_snapshot
    saves_block = (
        snapshot.get("salvezze")
        if snapshot
        else {"Tempra": 4, "Riflessi": 3, "Volontà": 4}
    )
    skills_map = (
        {
            name: {"totale": value}
            for name, value in (snapshot.get("skills") if snapshot else {}).items()
        }
        if snapshot
        else {
            "Percezione": {"totale": 5},
            "Acrobazia": {"totale": 4},
            "Conoscenze": {"totale": 3},
        }
    )
    slot_text = (
        snapshot.get("slot")
        if snapshot and not is_cutpurse
        else ("Non incantatore" if is_cutpurse else "Liv1:4/Liv2:3")
    )
    spell_levels: list[dict[str, object]] = []
    slot_pattern = re.compile(
        r"(\d+)\s*(?:[°º]|lvl|liv(?:ello)?|level)?\s*[:=]?\s*(\d+)"
    )
    for level_str, per_day_str in slot_pattern.findall(slot_text or ""):
        try:
            level = int(level_str)
            per_day = int(per_day_str)
        except ValueError:
            continue
        if level <= 0:
            continue
        spell_levels.append({"liv": level, "per_day": per_day})
    ac_block = (
        snapshot.get("ca")
        if snapshot
        else {"totale": 18, "armatura": 5, "destrezza": 2, "scudo": 1}
    )
    if isinstance(ac_block, Mapping) and "scudo" not in ac_block:
        ac_block = {**ac_block, "scudo": 0}
    equip_full = []
    if wizard_levels:
        for entry in wizard_levels:
            equip_full.extend(entry.get("equip", []))
    elif cutpurse_levels:
        for entry in cutpurse_levels:
            equip_full.extend(entry.get("equip", []))
    else:
        equip_full.extend(["Arma preferita", "Armatura leggera"])
    inventory_full = ["Kit da avventuriero", "Pozione di cura x2"]
    talents_full: list[str] = []
    if wizard_levels:
        for entry in wizard_levels:
            talents_full.extend(entry.get("talenti", []))
    elif cutpurse_levels:
        for entry in cutpurse_levels:
            talents_full.extend(entry.get("talenti", []))
    else:
        talents_full.extend(["Colpo possente", "Iniziativa migliorata"])
    class_features: list[str] = []
    if wizard_levels:
        for entry in wizard_levels:
            class_features.extend(entry.get("privilegi", []))
    elif cutpurse_levels:
        for entry in cutpurse_levels:
            class_features.extend(entry.get("privilegi", []))
    else:
        class_features.extend(["Addestramento marziale", "Specializzazione"])

    base_cutpurse_stats = None
    if is_cutpurse:
        for entry in cutpurse_progression_plan:
            stats_candidate = entry.get("stats")
            if isinstance(stats_candidate, Mapping):
                base_cutpurse_stats = stats_candidate
                break
    stats_block = (
        snapshot.get("stats")
        if snapshot and isinstance(snapshot.get("stats"), Mapping)
        else (
            base_cutpurse_stats
            if base_cutpurse_stats is not None
            else {
                "FOR": 16,
                "DES": 14,
                "COS": 14,
                "INT": 10,
                "SAG": 12,
                "CAR": 8,
            }
        )
    )
    attack_text = snapshot.get("attacco") if snapshot else "+4"
    damage_text = snapshot.get("danni") if snapshot else "1d8+3"
    initiative_bonus = 4 if is_cutpurse else 2
    speed_value = 6 if is_cutpurse else 9
    skill_points = max(5 * resolved_level, 4 * resolved_level)
    if is_cutpurse:
        int_mod = (
            int((stats_block.get("INT") or 10) - 10) // 2
            if isinstance(stats_block.get("INT"), (int, float))
            else 0
        )
        skill_points = (8 + max(int_mod, 0)) * resolved_level

    sheet_payload = {
        "classi": [
            {
                "nome": class_name or "Unknown",
                "livelli": resolved_level,
                "archetipi": [resolved_archetype] if resolved_archetype else [],
            }
        ],
        "statistiche": stats_block,
        "statistiche_chiave": {
            "attacco": attack_text,
            "danni": damage_text,
            "ca": (
                ac_block.get("totale", 17) if isinstance(ac_block, Mapping) else 17
            ),
        },
        "pf_totali": base_hp,
        "hp": {"totali": base_hp, "per_livello": hp_progression},
        "salvezze": saves_block,
        "skills_map": skills_map,
        "skill_points": skill_points,
        "talenti": sorted(set(talents_full)),
        "capacita_classe": sorted(set(class_features)),
        "equipaggiamento": sorted(set(equip_full)),
        "inventario": sorted(set(inventory_full + equip_full)),
        "spell_levels": spell_levels,
        "slot_incantesimi": slot_text,
        "ac_breakdown": (
            ac_block
            if isinstance(ac_block, Mapping)
            else {"totale": 18, "armatura": 5, "destrezza": 2, "scudo": 1}
        ),
        "iniziativa": initiative_bonus,
        "velocita": speed_value,
        "progressione": progression,
        "benchmarks": {"meta_tier": "T3"},
        "hooks": (body or {}).get("hooks"),
    }

    export_block = {"sheet_payload": sheet_payload}

    base_build_state["statistics"] = sheet_payload["statistiche"]
    benchmark["statistics"] = sheet_payload["statistiche_chiave"]

    narrative = (
        f"{resolved_race or 'Avventuriero'} {resolved_archetype or 'Base'} pronta/o per il campo, "
        f"specializzata/o in tattiche da {class_name or 'classe'}."
    )
    ledger = {
        "movimenti": [
            {"voce": "Equipaggiamento iniziale", "importo": -150},
            {"voce": "Ricompensa missione", "importo": 250},
        ],
        "currency": {"oro": 100, "argento": 25, "rame": 40},
    }

    catalog_manifest = _load_reference_manifest()
    catalog_version = (
        str(catalog_manifest.get("version"))
        if isinstance(catalog_manifest, Mapping)
        else None
    )
    if not catalog_version:
        raise StubBuilderError(
            "Reference catalog manifest non disponibile",
            status_code=503,
        )

    payload: dict[str, Any] = {
        "build_state": base_build_state,
        "benchmark": benchmark,
        "export": export_block,
        "narrative": narrative,
        "sheet": sheet_payload,
        "ledger": ledger,
        "class": class_name,
        "mode": normalized_mode,
        "reference_catalog_version": catalog_version,
        "catalog_manifest": catalog_manifest,
    }

    payload["composite"] = {
        "build": {
            "build_state": payload["build_state"],
            "benchmark": payload["benchmark"],
            "export": payload["export"],
            "sheet_payload": sheet_payload,
            "reference_catalog_version": catalog_version,
        },
        "narrative": narrative,
        "sheet": payload["sheet"],
        "sheet_payload": sheet_payload,
        "ledger": ledger,
    }

    schema_filename = schema_for_mode(normalized_mode)
    try:
        validate_with_schema(
            schema_filename,
            payload,
            "minmax_builder_stub",
            strict=True,
        )
    except ValidationError as exc:
        raise StubBuilderError(
            f"Stub payload non valido per {schema_filename}: {exc}",
            status_code=500,
        ) from exc

    return payload
