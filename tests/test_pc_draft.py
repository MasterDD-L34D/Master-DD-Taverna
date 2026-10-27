"""Gate A2-a1 (piano planning/2026-10-27-a2a-banco-qualita-build.md): pc_draft.

Il banco di qualita' (a2) ricalcola le build con src/pc/build_character, che
richiede un CharacterDraft completo. pc_draft e' la sezione del payload che
lo rappresenta 1:1 (chiavi inglesi, punteggi base point-buy, campi
obbligatori) — D1 della review Claude: chiave nuova, mai 'sheet' (gia' usata
altrove). Il fallback DEVE popolarla: nessuna via libera dal banco.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from generate_build_db import validate_with_schema
from src.agents.builder import _build_fallback, _make_prompt

PC_DRAFT_VALIDA = {
    "name": "Test build",
    "method": "point-buy",
    "campaign_type": "Standard Fantasy",
    "abilities": {"str": 13, "dex": 13, "con": 13, "int": 12, "wis": 10, "cha": 10},
    "race": "Human",
    "class": "Fighter",
    "race_bonus_ability": "con",
    "favored_class_bonus": "hp",
    "level": 5,
    "hp_method": "average",
    "skills": {},
    "feats": [],
    "traits": [],
    "equipment": [],
    "spells": [],
}


def _payload(pc_draft):
    payload = _build_fallback({"class": "Fighter", "race": "Human", "level": 5}, [])
    payload["pc_draft"] = pc_draft
    return payload


def test_pc_draft_valida_passa_schema():
    assert (
        validate_with_schema(
            "build_core.schema.json", _payload(PC_DRAFT_VALIDA), "test", strict=True
        )
        is None
    )


def test_pc_draft_malformata_fallisce_schema():
    # chiavi italiane = drift del contratto 1:1 con CharacterDraft
    drift = dict(PC_DRAFT_VALIDA)
    drift["abilities"] = {
        "for": 13,
        "des": 13,
        "con": 13,
        "int": 12,
        "sag": 10,
        "car": 10,
    }
    # strict=False: ritorna il messaggio di errore senza raise (come il gate
    # del builder in _validate); il $def pc_draft deve renderlo non-None
    assert (
        validate_with_schema(
            "build_core.schema.json", _payload(drift), "test", strict=False
        )
        is not None
    )


def test_fallback_popola_pc_draft_valida():
    # nessuna via libera: il fallback stesso deve produrre un draft che
    # build_character accetta senza errori bloccanti
    from src.pc.engine import build_character
    from src.pc.models import CharacterDraft

    payload = _build_fallback({"class": "Fighter", "race": "Human", "level": 5}, [])
    sheet = build_character(CharacterDraft.from_dict(payload["pc_draft"]))
    assert sheet["errors"] == []


def test_prompt_chiede_pc_draft():
    prompt = _make_prompt({"class": "Fighter", "race": "Human", "level": 5}, [], [])
    assert "pc_draft" in prompt


def test_prompt_espone_catalogo_nomi_pc():
    # fix P2 review #562: race/class/skills devono poter rispettare
    # "nomi ESATTI dal catalogo" — il prompt espone i nomi veri, non solo
    # i source_id reference (feats/spells/items)
    prompt = _make_prompt({"class": "Fighter", "race": "Human", "level": 5}, [], [])
    assert "Catalogo nomi PC" in prompt
    assert "- Races:" in prompt and "Human" in prompt
    assert "- Classes:" in prompt and "Fighter" in prompt
    assert "- Skills:" in prompt and "Perception" in prompt
