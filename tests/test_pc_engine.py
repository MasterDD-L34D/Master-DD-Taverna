"""Test per src/pc/engine.py — step caratteristiche."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.engine import apply_abilities, build_character, render_markdown
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


def test_skill_rank_prereq():
    # Mounted Combat richiede "Ride 1 rank": senza Ride nel draft -> errore.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Mounted Combat"]))
    assert any("Mounted Combat" in e and "Ride" in e for e in sheet["errors"])
    # Con Ride 1 rank -> prerequisito soddisfatto.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Ride": 1, "Climb": 1, "Perception": 1},
                                   feats=["Mounted Combat"]))
    assert sheet["errors"] == [], sheet["errors"]


def test_ranks_above_one_fail():
    # Back to Back richiede "Perception 3 ranks": impossibile al lv1 -> errore.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Back to Back"]))
    assert any("Back to Back" in e and "3 ranks" in e for e in sheet["errors"])


def test_monk_bonus_feats():
    # Monk lv1 ha "Bonus feat" (classes.json): 1 base + 1 Human + 1 Monk = 3 talenti.
    # NB: Dodge escluso perche' richiede Dex 13 (con bonus razziale su Wis resta 12);
    # Combat Reflexes / Improved Unarmed Strike / Weapon Finesse non hanno prerequisiti.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="wis",
                                   **{"class": "Monk"},
                                   skills={"Climb": 1, "Perception": 1},
                                   feats=["Combat Reflexes", "Improved Unarmed Strike",
                                          "Weapon Finesse"]))
    assert sheet["errors"] == [], sheet["errors"]


def test_chain_missing():
    # Cleave richiede il talento Power Attack: non selezionato -> errore che lo menziona.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Cleave"]))
    assert any("Cleave" in e and "Power Attack" in e for e in sheet["errors"])


# Costi reali (equipment_mundane.json): Longsword 15 gp, Chain shirt 100 gp,
# Backpack (common) 2 gp, Full plate 1,500 gp. Fighter: average 175 gp.
def test_equipment_wealth_and_ac():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   equipment=["Longsword", "Chain shirt", "Backpack (common)"]))
    assert sheet["errors"] == [], sheet["errors"]
    # 15 + 100 + 2 = 117 su 175 -> restano 58
    assert sheet["gold_remaining"] == 58
    # CA = 10 + armor +4 (Chain shirt) + Dex mod 1 (Dex 12; max +4 non cappato) = 15
    assert sheet["ac"] == 15
    melee = [a for a in sheet["attacks"] if a["weapon"] == "Longsword"][0]
    assert melee["bonus"] == 3  # bab 1 + Str mod +2 (str finale 15)
    assert melee["damage"] == "1d8+2"  # dmg_m + Str mod


def test_equipment_over_wealth_and_unknown():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str", skills={"Climb": 1},
                                   equipment=["Chain shirt", "Full plate"]))
    assert any("wealth" in e.lower() or "oro" in e.lower() for e in sheet["errors"])
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str", skills={"Climb": 1},
                                   equipment=["Spada Inesistente"]))
    assert any("Spada Inesistente" in e for e in sheet["errors"])


# Euristica gittata: ranged solo se range >= 30 ft; le armi da lancio
# (Dagger 10 ft., Shortspear 20 ft., Club 10 ft.) restano melee.
def test_thrown_weapon_is_melee():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1}, equipment=["Dagger"]))
    assert sheet["errors"] == [], sheet["errors"]
    dagger = [a for a in sheet["attacks"] if a["weapon"] == "Dagger"][0]
    assert dagger["bonus"] == 3  # bab 1 + Str mod +2 (str 15), non Dex
    assert dagger["damage"] == "1d4+2"


def test_ranged_weapon():
    # Shortbow range 60 ft. -> ranged: Dex al tiro, niente mod al danno.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1}, equipment=["Shortbow"]))
    assert sheet["errors"] == [], sheet["errors"]
    bow = [a for a in sheet["attacks"] if a["weapon"] == "Shortbow"][0]
    assert bow["bonus"] == 2  # bab 1 + Dex mod +1 (Dex 12)
    assert bow["damage"] == "1d6"


def test_cp_sp_costs():
    # Torch 1 cp = 0.01 gp, Animal glue 5 sp = 0.5 gp: totale 0.51.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1},
                                   equipment=["Torch", "Animal glue"]))
    assert sheet["errors"] == [], sheet["errors"]
    costs = {it["name"]: it["cost"] for it in sheet["equipment"]}
    assert costs["Torch"] == 0.01
    assert costs["Animal glue"] == 0.5
    assert sheet["gold_remaining"] == 174.49


def test_max_dex_cap():
    # Dex 14 (12+2 razziale) -> mod +2, ma Full plate cappato a +1.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="dex",
                                   skills={"Climb": 1}, equipment=["Full plate"]))
    assert sheet["ac"] == 20  # 10 + 9 + 1 (cappato)


def test_multiple_armors_error():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1},
                                   equipment=["Chain shirt", "Full plate"]))
    assert any("indossabili" in e and "migliore" in e for e in sheet["errors"])
    # solo la migliore (Full plate +9, max dex +1) conta per la CA
    assert sheet["ac"] == 20  # 10 + 9 + Dex mod 1 (Dex 12, cappato a +1)


def test_traits_validation():
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   traits=["Reactionary", "Indomitable Faith"]))
    assert sheet["errors"] == []
    assert sheet["traits"] == ["Reactionary", "Indomitable Faith"]
    # 2 stessa categoria -> errore; 3 tratti -> errore
    bad = _draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                 skills={"Climb": 1, "Perception": 1, "Survival": 1},
                 traits=["Reactionary", "Indomitable Faith", "Armor Expert"])
    sheet = build_character(bad)
    assert any("tratt" in e.lower() for e in sheet["errors"])
    # (a) 2 tratti della stessa categoria (entrambi Basic (Combat)) -> errore dedicato
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   traits=["Reactionary", "Armor Expert"]))
    assert any("stessa categoria" in e for e in sheet["errors"])
    # (b) tratto sconosciuto -> errore dedicato
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="str",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   traits=["Non Esiste"]))
    assert any("tratto sconosciuto" in e for e in sheet["errors"])


def test_markdown_render():
    # Bonus razziale su Dex (14): Dodge (Dex 13) passa e la scheda resta senza errori,
    # altrimenti la guard di render_markdown restituirebbe la pagina errori.
    sheet = build_character(_draft(abilities=dict(_OK_ABILS), race_bonus_ability="dex",
                                   skills={"Climb": 1, "Perception": 1, "Survival": 1},
                                   feats=["Power Attack", "Dodge", "Cleave"],
                                   traits=["Reactionary", "Indomitable Faith"],
                                   equipment=["Longsword", "Chain shirt"]))
    md = render_markdown(sheet)
    assert "# T" in md and "PF: 12" in md and "Longsword" in md and "Power Attack" in md


def test_render_signed_negative():
    # str 7 -> mod -2; attacco Longsword = BAB 1 - 2 = -1: segno singolo, mai "+-".
    # Point-buy: 7(-4) 14(5) 14(5) 10(0) 12(2) 13(3) = 11 <= 15.
    abils = {"str": 7, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 13}
    sheet = build_character(_draft(abilities=abils, race_bonus_ability="dex",
                                   skills={"Climb": 1}, equipment=["Longsword"]))
    assert sheet["errors"] == [], sheet["errors"]
    md = render_markdown(sheet)
    assert "+-" not in md
    assert "Longsword -1 (1d8-2)" in md
