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
    # shape reale del gist: components stringa, spell_level stringa,
    # niente spell_resistance/descriptors (arrivano solo dalla description).
    entry = {"name": "Fireball",
             "description": ("School evocation [fire]; Level sorcerer/wizard 3. "
                             "Saving Throw Reflex half; Spell Resistance yes")}
    gist = {"fireball": {"school": "evocation",
                          "spell_level": "sorcerer/wizard 3, magus 3",
                          "components": "V, S, M (a ball of bat guano and sulfur)",
                          "range": "long (400 ft. + 40 ft./level)",
                          "saving_throw": "Reflex half"}}
    mech = merge_mechanics(entry, gist)
    assert mech["school"] == "evocation"
    assert mech["components"] == "V, S, M (a ball of bat guano and sulfur)"
    assert mech["spell_level"] == {"sorcerer/wizard": 3, "magus": 3}
    assert mech["descriptors"] == ["fire"]
    assert mech["spell_resistance"] == "yes"
    print("OK: spells mechanics merge")


def test_no_prose_leak_banishment():
    desc = ("School abjuration; Level cleric 7, sorcerer/wizard 7\n\n"
            "Casting Time 1 standard action\nComponents V, S, F\n\n"
            "Description: If the target wins its save, Spell Resistance applies (if any), and the saving throw DC increases by 2.")
    mech = parse_description_mechanics(desc)
    assert "saving throw DC" not in str(mech.get("spell_resistance", ""))
    assert mech["school"] == "abjuration"


def test_inverted_name_greater():
    gist = {"invisibility, greater": {"school": "illusion", "spell_level": {"sorcerer/wizard": 4}}}
    entry = {"name": "Greater Invisibility", "description": ""}
    mech = merge_mechanics(entry, gist)
    assert mech["school"] == "illusion"
    assert mech["spell_level"] == {"sorcerer/wizard": 4}
