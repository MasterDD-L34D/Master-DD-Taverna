"""Test per src/pc/catalogs.py (dati reali su disco, nessuna rete)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.catalogs import (
    ability_cost,
    campaign_budget,
    find_equipment,
    find_feat,
    find_trait,
    get_class,
    get_race,
    get_skill,
)


def test_ability_tables():
    assert ability_cost(7) == -4
    assert ability_cost(14) == 5
    assert ability_cost(18) == 17
    assert campaign_budget("Standard Fantasy") == 15
    assert campaign_budget("Epic Fantasy") == 25


def test_getters():
    human = get_race("Human")
    assert human["mechanics"]["ability_mods"] == {"any": 2}
    fighter = get_class("Fighter")
    assert fighter["mechanics"]["hd"] == "d10"
    assert len(fighter["mechanics"]["progression"]) == 20
    assert get_skill("Perception")["mechanics"]["key_ability"] == "wis"
    assert find_feat("Power Attack") is not None
    assert find_feat("Non Esiste") is None
    assert find_equipment("Longsword")["mechanics"]["cost"] == "15 gp"
    assert find_trait("Reactionary")["mechanics"]["category"] == "Basic (Combat)"
    print("OK: catalogs loaders")


def test_spell_lookup_is_case_insensitive():
    from src.pc.catalogs import find_spell

    spell = find_spell("Ray of Enfeeblement")
    assert spell is not None
    assert spell["name"] == "Ray Of Enfeeblement"


def test_non_mythic_feat_descriptions_do_not_contain_mythic_benefits():
    improved = find_feat("Improved Initiative")
    assert improved["description"] == (
        "Your quick reflexes allow you to react rapidly to danger.\n\n"
        "You get a +4 bonus on initiative checks."
    )

    spell_focus = find_feat("Spell Focus")
    assert spell_focus["description"] == (
        "Choose a school of magic. Any spells you cast of that school are more difficult to resist.\n\n"
        "Add +1 to the Difficulty Class for all saving throws against spells from the school of magic you select.\n\n"
        "You can gain this feat multiple times. Its effects do not stack. "
        "Each time you take the feat, it applies to a new school of magic."
    )
