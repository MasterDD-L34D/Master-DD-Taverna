"""Test per tools/expand_monsters.py — split/convert del dataset espanso."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.expand_monsters import split_and_convert


def _obj(name, kind, cr=5):
    return {
        "title1": name,
        "title2": name,
        "CR": cr,
        "XP": 1600,
        "sources": [{"name": "Bestiary 2", "page": 42}],
        "alignment": {"raw": "NE", "cleaned": "NE"},
        "size": "Medium",
        "type": "outsider",
        "HP": {"total": 45, "long": "5d10+15"},
        "AC": {"AC": 18, "touch": 12, "flat_footed": 16},
        "saves": {"fort": 6, "ref": 5, "will": 4},
        "desc_short": f"{name} short.",
        "_kind": kind,
    }


def test_split_and_convert_kinds_tags_dedup():
    objects = {
        "u1": _obj("Alpha", "monsters"),
        "u2": _obj("Beta", "mythic"),
        "u3": _obj("Gamma", "npcs"),
        "u4": _obj("Alpha", "monsters"),  # duplicato: scartato (tiene il primo)
    }
    monsters, npcs = split_and_convert(objects)
    assert [e["name"] for e in monsters] == ["Alpha", "Beta"]
    assert [e["name"] for e in npcs] == ["Gamma"]
    beta = monsters[1]
    assert "mythic" in beta["tags"]
    assert "monster" in beta["tags"]
    assert "npc" in npcs[0]["tags"] and "monster" not in npcs[0]["tags"]
    # mechanics v2 preservati dal convert
    assert monsters[0]["mechanics"]["cr"] == 5
    assert monsters[0]["mechanics"]["type"] == "outsider"
