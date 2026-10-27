"""Test per tools/import_monsters.py — mechanics da fonte strutturata."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_monsters import convert_monsters

# Entry REALE copiata da PathfinderMonsterDatabase data/full/data.json
# ("Aashaq's Wyvern"), ridotta ai campi principali.
SOURCE_SAMPLE = [
    {
        "title1": "Aashaq's Wyvern",
        "title2": "Aashaq's Wyvern",
        "CR": 8,
        "XP": 4800,
        "sources": [{"name": "Isles of the Shackles", "page": 42}],
        "alignment": {"raw": "CN", "cleaned": "CN"},
        "size": "Large",
        "type": "dragon",
        "initiative": {"bonus": 5},
        "senses": {"darkvision": 60, "low-light vision": True, "scent": True},
        "AC": {
            "AC": 20,
            "touch": 10,
            "flat_footed": 19,
            "components": {"dex": 1, "natural": 10, "size": -1},
        },
        "HP": {
            "total": 103,
            "long": "9d12+45",
            "HD": {"racial": {"die": 12, "num": 9}, "num": 9},
            "bonus_HP": 45,
        },
        "saves": {"fort": 11, "ref": 7, "will": 9},
        "immunities": ["dragon traits", "magic paralysis and sleep"],
        "resistances": {"acid": 10, "fire": 10},
        "SR": 19,
        "speeds": {"base": 20, "fly": 60, "fly_maneuverability": "poor", "swim": 40},
        "attacks": {
            "melee": [
                [
                    {
                        "text": "bite +13 (2d6+5 plus grab)",
                        "attack": "bite",
                        "bonus": [13],
                    },
                    {
                        "text": "2 stings +13 (1d6+5 plus poison)",
                        "count": 2,
                        "attack": "stings",
                        "bonus": [13],
                    },
                ]
            ],
            "special": [
                "breath weapon (30-ft. cone, 6d6 fire damage plus fumes, "
                "Reflex DC 19 half, usable every 1d4 rounds)"
            ],
        },
        "space": 10,
        "reach": 5,
        "ability_scores": {
            "STR": 21,
            "DEX": 12,
            "CON": 20,
            "INT": 9,
            "WIS": 12,
            "CHA": 11,
        },
        "BAB": 9,
        "CMB": 15,
        "CMD": 26,
        "feats": [{"name": "Combat Reflexes"}, {"name": "Flyby Attack"}],
        "skills": {"Fly": {"_": 7}, "Perception": {"_": 20}},
        "special_abilities": {
            "Poison (Ex)": "Sting-injury; save Fort DC 19; frequency 1/round "
            "for 6 rounds; effect 1d4 Con; cure 2 consecutive saves.",
        },
        "ecology": {
            "environment": "temperate or warm hills",
            "organization": "solitary, pair, or murder (3-5 and 1-3 wyverns)",
            "treasure_type": "standard",
        },
        "subtypes": ["evil"],
        "special_qualities": ["hold breath"],
        "CMB_other": "+19 grapple",
        "CMD_other": "can't be tripped",
        "spell_like_abilities": {"constant": ["detect magic"]},
        "desc_short": "This light purple dragon has immense wings and a bifurcated tail.",
    }
]


def test_convert_monsters_emits_mechanics():
    entries = convert_monsters(SOURCE_SAMPLE)
    assert len(entries) == 1
    e = entries[0]
    assert "mechanics" in e
    mech = e["mechanics"]
    assert mech["cr"] == 8
    assert mech["xp"] == 4800
    assert mech["ac"] == 20
    assert mech["touch"] == 10
    assert mech["flat_footed"] == 19
    assert mech["hp"] == 103
    assert mech["hd"] == "9d12+45"
    assert mech["saves"]["fort"] == 11
    assert mech["saves"]["ref"] == 7
    assert mech["saves"]["will"] == 9
    assert mech["bab"] == 9
    assert mech["cmb"] == 15
    assert mech["cmd"] == 26
    assert mech["ability_scores"]["STR"] == 21
    assert mech["ability_scores"]["CHA"] == 11
    assert mech["speeds"]["fly"] == 60
    assert mech["senses"]["darkvision"] == 60
    assert mech["sr"] == 19
    assert mech["resistances"] == {"acid": 10, "fire": 10}
    assert "dragon traits" in mech["immunities"]
    assert mech["attacks"]["melee"][0][0]["attack"] == "bite"
    assert "Poison (Ex)" in mech["special_abilities"]
    assert mech["feats"][0]["name"] == "Combat Reflexes"
    assert "Perception" in mech["skills"]
    # retrocompatibilita' RAG: description inline conservata
    assert "Statblock:" in e["description"]
    print("OK: mechanics mostri da fonte")


def test_convert_monsters_missing_fields_use_none():
    """Campi assenti nella fonte -> None, niente KeyError."""
    minimal = [{"title1": "Blob", "CR": 1, "sources": [{"name": "Test"}]}]
    entries = convert_monsters(minimal)
    mech = entries[0]["mechanics"]
    assert mech["cr"] == 1
    assert mech["ac"] is None
    assert mech["saves"]["fort"] is None
    assert mech["dr"] is None
    assert mech["weaknesses"] is None


def test_convert_monsters_emits_v2_filter_and_combat_fields():
    """Mostri v2: campi filtro Encounter_Designer + blocco combat."""
    entries = convert_monsters(SOURCE_SAMPLE)
    mech = entries[0]["mechanics"]
    # filtri
    assert mech["type"] == "dragon"
    assert mech["size"] == "Large"
    assert mech["alignment"] == "CN"
    assert mech["initiative"] == 5
    assert mech["environment"] == "temperate or warm hills"
    assert mech["organization"].startswith("solitary")
    # combat
    assert mech["space"] == 10
    assert mech["reach"] == 5
    assert mech["subtypes"] == ["evil"]
    assert mech["special_qualities"] == ["hold breath"]
    assert mech["cmb_other"] == "+19 grapple"
    assert mech["cmd_other"] == "can't be tripped"
    assert mech["spell_like_abilities"] == {"constant": ["detect magic"]}
    print("OK: mechanics v2 filtro + combat")


def test_convert_monsters_v2_missing_fields_use_none():
    """Campi v2 assenti nella fonte -> None, niente KeyError."""
    minimal = [{"title1": "Blob", "CR": 1, "sources": [{"name": "Test"}]}]
    mech = convert_monsters(minimal)[0]["mechanics"]
    for key in (
        "type",
        "size",
        "alignment",
        "initiative",
        "environment",
        "organization",
        "subtypes",
        "space",
        "reach",
        "reach_other",
        "spell_like_abilities",
        "spells",
        "psychic_magic",
        "auras",
        "defensive_abilities",
        "special_qualities",
        "cmb_other",
        "cmd_other",
    ):
        assert key in mech, f"chiave mancante: {key}"
        assert mech[key] is None, f"{key} dovrebbe essere None"


def test_url_composite_names_use_subtype_page():
    """C3 (2026-07-25): nomi "Gruppo, Sottotipo" -> pagina del sottotipo AoN.

    Il nome intero ("Agathion, Leonal") risponde 500 su MonsterDisplay; la
    pagina esiste solo come "Leonal". Gruppi parentetici ("Dragon (Black),
    Adult Black Dragon") saltano alla virgola dopo la parentesi chiusa.
    """
    from tools.import_monsters import _url

    assert _url("Agathion, Leonal").endswith("ItemName=Leonal")
    assert _url("Devil, Host Devil, Greater (Magaav)").endswith(
        "ItemName=Host%20Devil,%20Greater%20(Magaav)"
    )
    assert _url("Dragon (Black), Adult Black Dragon").endswith(
        "ItemName=Adult%20Black%20Dragon"
    )
    assert _url("Dragon (Esoteric, Astral), Young Astral Dragon").endswith(
        "ItemName=Young%20Astral%20Dragon"
    )
    assert _url("Wyvern").endswith("ItemName=Wyvern")
