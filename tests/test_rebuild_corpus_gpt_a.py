"""Test per tools/rebuild_corpus_gpt_a.py (Lotto A, G1).

Copre:
- allineamento tabella decisioni <-> registry `_oracle_defects.json`
  (26 build: una decisione per ogni build flaggata, niente extra);
- budget point-buy: ogni statline della tabella costa <= 25 (Epic Fantasy)
  e le statline "tieni GPT" lette dal corpus restano <= 25;
- il builder `src/pc` accetta ogni draft corretto ai tre livelli (1/5/10)
  senza errori (conteggio talenti, prerequisiti, flex, skill);
- la riscrittura del payload: stats pre-razziali in tutte le copie
  ridondanti, talenti corretti, contratto E6-A6, derivati dal builder,
  sheet_payload.statistiche garantito anche se assente nella sorgente;
- idempotenza: applicare due volte la riscrittura non cambia il risultato.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.rebuild_corpus_gpt_a as rb
from src.pc.engine import build_character
from src.pc.models import CharacterDraft

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDS = REPO_ROOT / "src" / "data" / "builds"


def _registry_stems():
    registry = json.loads((BUILDS / "_oracle_defects.json").read_text(encoding="utf-8"))
    return {f[: -len(".json")] for f in registry["defects"]}


def test_tabella_allineata_al_registry():
    # Scope congelato lotto A: 26 build. Il registry si svuota dopo il
    # rebuild: la tabella resta un sopra-insieme (ogni build flaggata ha
    # una decisione), mai il contrario.
    assert len(rb.DECISIONS) == 26
    assert _registry_stems() <= set(rb.DECISIONS)


def test_statline_entro_budget_25():
    for stem, decision in rb.DECISIONS.items():
        if decision["stats"] is not None:
            cost = rb.point_buy_cost(decision["stats"])
            assert cost <= 25, f"{stem}: costo {cost} oltre 25"
            assert set(decision["stats"]) == set(rb._STATS_SHORT)


def test_statline_mantenute_legali():
    for stem, decision in rb.DECISIONS.items():
        if decision["stats"] is None:
            payload = json.loads((BUILDS / f"{stem}.json").read_text(encoding="utf-8"))
            assert rb.point_buy_cost(rb._current_stats(payload)) <= 25, stem


def test_builder_accetta_tutti_i_draft():
    for stem in rb.DECISIONS:
        payload = json.loads((BUILDS / f"{stem}.json").read_text(encoding="utf-8"))
        for level in (1, 5, 10):
            draft, _ = rb.build_draft(stem, payload, rb.DECISIONS[stem], level)
            sheet = build_character(CharacterDraft.from_dict(draft))
            assert not sheet.get("errors"), f"{stem} lv{level}: {sheet['errors']}"


def _minimal_payload():
    return {
        "build_state": {
            "class": "Fighter",
            "race": "Dwarf",
            "statistics": {
                "FOR": 16,
                "DES": 14,
                "COS": 14,
                "INT": 10,
                "SAG": 12,
                "CAR": 8,
                "Forza": 16,
                "forza": 16,
            },
        },
        "export": {
            "sheet_payload": {
                "classi": [{"nome": "Fighter", "livelli": 1}],
                "statistiche": {
                    "FOR": 16,
                    "DES": 14,
                    "COS": 14,
                    "INT": 10,
                    "SAG": 12,
                    "CAR": 8,
                    "ca": 18,
                },
                "talenti": ["Colpo possente", "Iniziativa migliorata"],
                "pf_totali": 12,
                "salvezze": {"Tempra": 4, "Riflessi": 3, "Volontà": 4},
                "iniziativa": 2,
                "skill_points": 2,
                "skills_map": {"Percezione": {"totale": 5}},
                "skills": [{"nome": "Percezione", "gradi": 1, "totale": 5}],
                "progressione": [
                    {"livello": 1, "talenti": ["Colpo possente"]},
                    {"livello": 2, "talenti": ["Talento di livello 2"]},
                ],
            }
        },
        "composite": {
            "build": {
                "sheet_payload": {
                    "classi": [{"nome": "Fighter", "livelli": 1}],
                    "statistiche": {
                        "FOR": 16,
                        "DES": 14,
                        "COS": 14,
                        "INT": 10,
                        "SAG": 12,
                        "CAR": 8,
                    },
                    "talenti": ["Colpo possente", "Iniziativa migliorata"],
                }
            }
        },
    }


def _fighter_sheet():
    draft = {
        "name": "t",
        "method": "point-buy",
        "campaign_type": "Epic Fantasy",
        "abilities": {"str": 15, "dex": 13, "con": 14, "int": 10, "wis": 12, "cha": 8},
        "race": "Human",
        "class": "Fighter",
        "level": 1,
        "race_bonus_ability": "str",
        "feats": ["Colpo possente"],
        "skills": {"Perception": 1},
    }
    return build_character(CharacterDraft.from_dict(draft))


def test_riscrittura_allinea_tutte_le_copie():
    payload = _minimal_payload()
    decision = {
        "stats": {"FOR": 15, "DES": 13, "COS": 14, "INT": 10, "SAG": 12, "CAR": 8},
        "feats": ["Colpo possente"],
        "flex": "FOR",
        "note": "test",
    }
    sheet = _fighter_sheet()
    stats_it = decision["stats"]
    pairs = [("Percezione", sheet["skills"]["Perception"])]
    out = rb.rebuild_payload(payload, sheet, decision, 1, stats_it, pairs, 2)

    sp = out["export"]["sheet_payload"]
    assert sp["statistiche"]["FOR"] == 15
    assert sp["bonus_razziale_flessibile"] == "FOR"
    assert sp["rebuild_gpt_a"]["livello"] == 1
    assert sp["talenti"] == ["Colpo possente"]
    assert sp["pf_totali"] == sheet["hp"]
    assert sp["salvezze"]["Tempra"] == sheet["saves"]["fort"]
    assert sp["iniziativa"] == sheet["initiative"]
    assert sp["skills_map"] == {
        "Percezione": {"totale": sheet["skills"]["Perception"]["total"]}
    }
    assert sp["progressione"][0]["talenti"] == ["Colpo possente"]
    assert sp["progressione"][1]["talenti"] == []
    # copie ridondanti allineate
    assert out["build_state"]["statistics"]["FOR"] == 15
    assert out["build_state"]["statistics"]["Forza"] == 15
    assert out["build_state"]["statistics"]["forza"] == 15
    nested = out["composite"]["build"]["sheet_payload"]
    assert nested["statistiche"]["FOR"] == 15
    assert nested["talenti"] == ["Colpo possente"]
    assert nested["bonus_razziale_flessibile"] == "FOR"
    # sorgente intatta (deep copy)
    assert payload["export"]["sheet_payload"]["statistiche"]["FOR"] == 16


def test_riscrittura_garantisce_statistiche_mancanti():
    payload = _minimal_payload()
    payload["export"]["sheet_payload"]["statistiche"] = None  # caso magus_kitsune
    decision = {
        "stats": {"FOR": 15, "DES": 13, "COS": 14, "INT": 10, "SAG": 12, "CAR": 8},
        "feats": ["Colpo possente"],
        "flex": None,
        "note": "test",
    }
    out = rb.rebuild_payload(
        payload, _fighter_sheet(), decision, 1, decision["stats"], [], 2
    )
    stats = out["export"]["sheet_payload"]["statistiche"]
    assert stats["FOR"] == 15 and stats["CAR"] == 8
    assert "bonus_razziale_flessibile" not in out["export"]["sheet_payload"]


def test_idempotenza():
    payload = _minimal_payload()
    decision = {
        "stats": {"FOR": 15, "DES": 13, "COS": 14, "INT": 10, "SAG": 12, "CAR": 8},
        "feats": ["Colpo possente"],
        "flex": "FOR",
        "note": "test",
    }
    sheet = _fighter_sheet()
    pairs = [("Percezione", sheet["skills"]["Perception"])]
    once = rb.rebuild_payload(payload, sheet, decision, 1, decision["stats"], pairs, 2)
    twice = rb.rebuild_payload(once, sheet, decision, 1, decision["stats"], pairs, 2)
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)


def test_dry_run_non_scrive(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rb, "BUILDS_DIR", tmp_path)
    monkeypatch.setattr(rb, "REGISTRY_PATH", tmp_path / "_oracle_defects.json")
    monkeypatch.setattr(rb, "ARCHIVE_DIR", tmp_path / "archive")
    (tmp_path / "_oracle_defects.json").write_text(
        json.dumps({"defects": {f"{s}.json": {} for s in rb.DECISIONS}}),
        encoding="utf-8",
    )
    (tmp_path / "fighter_dwarf_shielded.json").write_text(
        json.dumps(_minimal_payload()), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys, "argv", ["rebuild", "--dry-run", "--only", "fighter_dwarf_shielded"]
    )
    assert rb.main() == 0
    out = capsys.readouterr().out
    assert "fighter_dwarf_shielded" in out
    # dry-run: nessun file scritto oltre ai due creati dal test
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "_oracle_defects.json",
        "fighter_dwarf_shielded.json",
    ]
