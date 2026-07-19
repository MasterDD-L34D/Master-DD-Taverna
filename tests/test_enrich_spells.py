"""Test per tools/enrich_spells.py — mechanics spells via gist join + regex."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.enrich_spells import parse_description_mechanics, merge_mechanics


def test_parse_description_mechanics():
    desc = ("School evocation [fire]; Level sorcerer/wizard 3\n\n"
            "Casting Time 1 standard action\nComponents V, S, M\n\n"
            "Range medium (100 ft. + 10 ft./level)\nDuration instantaneous\n"
            "Saving Throw Reflex half; Spell Resistance yes")
    mech = parse_description_mechanics(desc)
    assert mech["school"] == "evocation"
    assert mech["descriptors"] == ["fire"]
    assert mech["spell_level"] == {"sorcerer/wizard": 3}
    assert mech["casting_time"] == "1 standard action"
    assert mech["saving_throw"] == "Reflex half"
    assert mech["spell_resistance"] == "yes"


def test_parse_multiclass_level():
    desc = "School abjuration; Level cleric 3, paladin 2, sorcerer/wizard 3"
    mech = parse_description_mechanics(desc)
    assert mech["spell_level"] == {"cleric": 3, "paladin": 2, "sorcerer/wizard": 3}


def test_merge_mechanics_gist_priority():
    entry = {"name": "Fireball", "description": "School evocation; Level sorcerer/wizard 3"}
    gist = {"fireball": {"school": "evocation", "spell_level": {"sorcerer/wizard": 3},
                          "components": ["V", "S", "M"], "range": "medium",
                          "saving_throw": "Reflex half", "spell_resistance": True}}
    mech = merge_mechanics(entry, gist)
    assert mech["school"] == "evocation"
    assert mech["components"] == ["V", "S", "M"]
    assert mech["spell_resistance"] in (True, "yes")
    print("OK: spells mechanics merge")
