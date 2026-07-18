"""Test per src/pc/engine.py — step caratteristiche."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.engine import apply_abilities, build_character
from src.pc.models import CharacterDraft


def _draft(**kw):
    base = {"name": "T", "method": "point-buy", "campaign_type": "Standard Fantasy",
            "abilities": {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 15, "cha": 11},
            "race": "Human", "class": "Fighter"}
    base.update(kw)
    return CharacterDraft.from_dict(base)


def test_point_buy_over_budget():
    sheet = apply_abilities(_draft())  # costa 18 su budget 15
    assert any("budget" in e.lower() for e in sheet["errors"])


def test_within_budget_with_racial_bonus():
    # 13(3) 12(2) 13(3) 10(0) 14(5) 12(2) = 15 <= 15
    sheet = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                             "int": 10, "wis": 14, "cha": 12},
                                   race_bonus_ability="str"))
    assert sheet["errors"] == []
    assert sheet["abilities"]["str"] == 15  # 13 + 2 any Human


def test_over_budget_and_missing_any_choice():
    sheet = apply_abilities(_draft())  # costa 18 su 15
    assert any("budget" in e.lower() for e in sheet["errors"])
    sheet2 = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                              "int": 10, "wis": 14, "cha": 12}))
    assert any("race_bonus_ability" in e for e in sheet2["errors"])


def test_dwarf_negative_mods():
    sheet = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                             "int": 10, "wis": 14, "cha": 12},
                                   race="Dwarf"))
    assert sheet["errors"] == []
    assert sheet["abilities"]["con"] == 15  # 13 + 2
    assert sheet["abilities"]["wis"] == 16  # 14 + 2
    assert sheet["abilities"]["cha"] == 10  # 12 - 2


def test_half_orc_any_bonus():
    sheet = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                             "int": 10, "wis": 14, "cha": 12},
                                   race="Half-Orc", race_bonus_ability="con"))
    assert sheet["errors"] == []
    assert sheet["abilities"]["con"] == 15  # 13 + 2 any Half-Orc


def test_invalid_score_range():
    sheet = apply_abilities(_draft(abilities={"str": 19, "dex": 12, "con": 13,
                                             "int": 10, "wis": 14, "cha": 12}))
    assert sheet["errors"]
    sheet2 = apply_abilities(_draft(abilities={"str": 13, "dex": 12, "con": 13,
                                              "int": 10, "wis": 14}))
    assert sheet2["errors"]


# Set point-buy valido (15/15): str 15 dopo il bonus razziale +2.
_OK_ABILS = {"str": 13, "dex": 12, "con": 13, "int": 10, "wis": 14, "cha": 12}


def test_fighter_lv1_combat_basics():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1}))
    assert sheet["errors"] == []
    assert sheet["hp"] == 12  # d10 max + Con mod 1 (13) + favored hp 1
    assert sheet["saves"] == {"fort": 3, "ref": 1, "will": 2}  # base 2/0/0 + Con1/Dex1/Wis2
    assert sheet["bab"] == 1
    assert sheet["initiative"] == 1  # Dex 12 -> +1


def test_skill_points_and_totals():
    # Fighter 2 + Int 0 + Human 1 = 3 ranks max; 4 ranks -> errore
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1,
                                           "Intimidate": 1}))
    assert any("skill" in e.lower() for e in sheet["errors"])
    # 3 ranks ok: Climb di classe (+3), Perception NON di classe Fighter
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1}))
    assert sheet["errors"] == []
    assert sheet["skills"]["Climb"]["total"] == 1 + 2 + 3  # rank1 + Str mod 2 (15) + class 3
    assert sheet["skills"]["Perception"]["total"] == 1 + 2  # rank1 + Wis mod 2 (no class bonus)


def _wizard_draft(**kw):
    # Int 10 + 2 razziale = 12 -> mod +1; budget skill = 2 + 1 + 1 Human = 4.
    return _draft(abilities=dict(_OK_ABILS), race_bonus_ability="int", **{"class": "Wizard"}, **kw)


def test_knowledge_class_skill_bonus():
    # "Knowledge (all)" del Wizard matcha Knowledge (Arcana); anche Spellcraft e' di classe.
    sheet = build_character(_wizard_draft(skills={"Knowledge (Arcana)": 1, "Spellcraft": 1}))
    assert sheet["errors"] == []
    assert sheet["skills"]["Knowledge (Arcana)"]["total"] == 1 + 1 + 3  # rank + Int 1 (12) + class
    assert sheet["skills"]["Knowledge (Arcana)"]["class_skill"] is True
    assert sheet["skills"]["Spellcraft"]["total"] == 1 + 1 + 3
    assert sheet["skills"]["Spellcraft"]["class_skill"] is True


def test_wizard_lv1_basics():
    sheet = build_character(_wizard_draft(skills={"Knowledge (Arcana)": 1, "Spellcraft": 1}))
    assert sheet["errors"] == []
    assert sheet["hp"] == 8  # d6 max 6 + Con mod 1 (13) + favored hp 1
    assert sheet["saves"] == {"fort": 1, "ref": 1, "will": 4}  # base 0/0/2 + Con1/Dex1/Wis2
    assert sheet["bab"] == 0


def test_favored_bonus_invalid():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   favored_class_bonus="HP"))
    assert any("favored" in e.lower() for e in sheet["errors"])


# Prerequisiti reali (feats.json): Power Attack "Strength 13", Dodge "Dexterity 13",
# Cleave "Strength 13" + "Power Attack", Combat Expertise "Intelligence 13",
# Weapon Finesse nessuno, Combat Casting "Ability to cast spells" (non valutabile).
def test_feat_count_and_prereqs():
    # 3 feat per Human Fighter (1 base + 1 human + 1 fighter).
    # Bonus razziale su Dex: Dex 14 (Dodge ok), Str 13 basta per Power Attack e Cleave.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="dex",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Power Attack", "Dodge", "Cleave"]))
    assert sheet["errors"] == [], sheet["errors"]
    assert sheet["feats"] == ["Power Attack", "Dodge", "Cleave"]


def test_feat_prereq_failures():
    # Str 12 (<13): Power Attack e Cleave falliscono; e 4 feat su 3 consentiti.
    d = _draft(abilities={"str": 12, "dex": 13, "con": 13, "int": 10, "wis": 14, "cha": 12},
               race_bonus_ability="dex", skills={"Climb": 1, "Perception": 1, "Survival": 1},
               feats=["Power Attack", "Dodge", "Cleave", "Weapon Finesse"])
    sheet = build_character(d)
    assert any("Power Attack" in e and "Str" in e for e in sheet["errors"])
    assert any("feat" in e.lower() and "3" in e for e in sheet["errors"])


def test_unverifiable_prereq_is_warning():
    # Int 14 (13+1 razziale su Str): Combat Expertise (Int 13) passa.
    # Combat Casting richiede "Ability to cast spells": forma non valutabile -> warning.
    abils = {"str": 13, "dex": 12, "con": 13, "int": 14, "wis": 12, "cha": 10}  # 15/15
    sheet = build_character(_draft(abilities=abils, race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Combat Expertise", "Combat Casting"]))
    assert sheet["errors"] == [], sheet["errors"]
    assert any("Combat Casting" in w and "non valutabile" in w for w in sheet["warnings"])


def test_class_level_prereq_threshold():
    # Spell Focus richiede "caster level 1st": un Wizard lv1 lo soddisfa.
    # NB: per cambiare classe serve _wizard_draft (o "class" come chiave):
    # class_="Wizard" passato a _draft verrebbe sovrascritto da from_dict.
    sheet = build_character(_wizard_draft(skills={"Spellcraft": 1, "Knowledge (Arcana)": 1},
                                          feats=["Spell Focus"]))
    assert sheet["errors"] == [], sheet["errors"]
    # Weapon Specialization richiede "fighter level 4th" (+ Weapon Focus...): fallisce al lv1.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Weapon Specialization"]))
    assert any("Weapon Specialization" in e for e in sheet["errors"])
