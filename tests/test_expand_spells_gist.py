"""Test per tools/expand_spells_gist.py — espansione spells da cache gist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.expand_spells_gist import gist_to_entry, is_pi_name, new_gist_records

GIST_SAMPLE = {
    "name": "Ablative Sphere",
    "source": "Ultimate Magic",
    "school": "abjuration",
    "spell_level": "sorcerer/wizard 3",
    "casting_time": "1 standard action",
    "components": "V, S, M (a crystalline sphere worth 10 gp)",
    "range": "personal",
    "duration": "1 minute per level (D)",
    "saving_throw": "",
    "targets": "you",
    "description": "An immobile, crystalline globe surrounds you.",
}


def test_gist_to_entry_builds_catalog_shape():
    e = gist_to_entry(GIST_SAMPLE)
    assert e["name"] == "Ablative Sphere"
    assert e["source"] == "Ultimate Magic"
    assert e["source_id"] == "pathfinder_srd:ablative_sphere"
    assert e["prerequisites"] == []
    assert "school:abjuration" in e["tags"]
    assert "slot:3" in e["tags"]
    assert "class:sorcerer" in e["tags"] and "class:wizard" in e["tags"]
    assert e["reference_urls"] == [
        "https://aonprd.com/SpellDisplay.aspx?ItemName=Ablative%20Sphere"
    ]
    mech = e["mechanics"]
    assert mech["school"] == "abjuration"
    assert mech["spell_level"] == {"sorcerer/wizard": 3}
    assert mech["targets"] == "you"
    assert "saving_throw" not in mech  # campo gist vuoto -> omesso
    assert "gist" in e["notes"].lower()


def test_new_gist_records_skips_existing_and_inverted():
    local_names = ["Acid Arrow", "Greater Invisibility"]
    gist = [
        {"name": "Acid Arrow"},  # gia' presente
        {"name": "Invisibility, Greater"},  # forma invertita di una locale
        {"name": "Ablative Sphere"},  # nuova
    ]
    nuovi = new_gist_records(local_names, gist)
    assert [g["name"] for g in nuovi] == ["Ablative Sphere"]


def test_is_pi_name_flags_deity_possessive():
    assert is_pi_name("Abadar's Truthtelling")
    assert is_pi_name("Iomedae's Sword")
    assert not is_pi_name("Ablative Sphere")
    assert not is_pi_name("Fireball")


def test_description_sanitized_word_boundary():
    g = dict(GIST_SAMPLE)
    g["description"] = "This spell is common on Golarion. The globe protects you."
    e = gist_to_entry(g)
    assert "Golarion" not in e["description"]
