"""Test per src/pc/catalogs.py (dati reali su disco, nessuna rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pc.catalogs import (ability_cost, campaign_budget, find_equipment,
                             find_feat, find_trait, get_class, get_race,
                             get_skill)


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
