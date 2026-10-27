"""Test per tools/import_archetypes.py — parse indici archetipi AoN."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_archetypes import (
    archetype_entry,
    parse_archetype_features,
    parse_archetypes,
)

# Markup ricalcato sulla pagina reale Archetypes.aspx?Class=Fighter
# (cache 2026-07-25): header <td><b>Name</b>..., celle con <a> + <img> PFS.
FIGHTER_HTML = """
<html><body>
<h1 class="title">Fighter Archetypes</h1>
<table>
<tr><td><b>Name</b></td><td><b>Replaces</b></td><td><b>Summary</b></td></tr>
<tr><td><a href="ArchetypeDisplay.aspx?FixedName=Fighter Aerial Assaulter"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Aerial Assaulter</a></td><td>Class Skills; Bravery; Armor Mastery, Weapon Mastery</td><td>Aerial assaulters leap to great heights.</td></tr>
<tr><td><a href="ArchetypeDisplay.aspx?FixedName=Fighter Airborne Ambusher">Airborne Ambusher</a></td><td>Weapon/Armor Proficiency; Weapon Training 1-4 (Strix Only)</td><td>(Strix Only) Driven by suspicion, strix guard their territories.</td></tr>
<tr><td><a href="ArchetypeDisplay.aspx?FixedName=Druid Treesinger">Treesinger</a></td><td>Nature Bond; Wild Empathy (Elf and Vine Leshy Only)</td><td>Elves turn to the growth of nature for solace.</td></tr>
</table>
</body></html>
"""


def test_parse_archetypes_table():
    rows = parse_archetypes(FIGHTER_HTML)
    assert len(rows) == 3
    r0 = rows[0]
    assert r0["name"] == "Aerial Assaulter"
    assert r0["replaces"] == [
        "Class Skills",
        "Bravery",
        "Armor Mastery, Weapon Mastery",
    ]
    assert r0["race_req"] is None
    assert r0["summary"] == "Aerial assaulters leap to great heights."
    assert r0["detail_url"] == (
        "https://aonprd.com/ArchetypeDisplay.aspx"
        "?FixedName=Fighter%20Aerial%20Assaulter"
    )
    r1 = rows[1]
    assert r1["race_req"] == ["Strix"]
    # il marcatore razziale e' rimosso dagli item replaces e dalla summary
    assert r1["replaces"] == ["Weapon/Armor Proficiency", "Weapon Training 1-4"]
    assert "Only" not in r1["summary"]
    assert r1["summary"].startswith("Driven by suspicion")
    # marcatore composito '(X and Y Only)' -> due requisiti (semantica OR)
    r2 = rows[2]
    assert r2["race_req"] == ["Elf", "Vine Leshy"]
    assert r2["replaces"] == ["Nature Bond", "Wild Empathy"]


def test_parse_archetypes_no_table():
    assert parse_archetypes("<html><body><p>nessuna tabella</p></body></html>") == []


def test_archetype_entry_catalog_shape():
    row = {
        "name": "Aerial Assaulter",
        "replaces": ["Class Skills", "Bravery"],
        "race_req": None,
        "summary": "Aerial assaulters leap to great heights.",
        "detail_url": "https://aonprd.com/ArchetypeDisplay.aspx?FixedName=Fighter%20Aerial%20Assaulter",
    }
    e = archetype_entry(row, "Fighter")
    assert e["name"] == "Aerial Assaulter"
    assert e["source_id"] == "archetype:fighter_aerial_assaulter"
    assert e["prerequisites"] == []
    assert "archetype" in e["tags"] and "fighter" in e["tags"]
    assert e["mechanics"] == {
        "class": "Fighter",
        "replaces": ["Class Skills", "Bravery"],
        "race_req": None,
    }
    assert e["reference_urls"][0] == "https://aonprd.com/Archetypes.aspx?Class=Fighter"
    assert e["reference_urls"][1] == row["detail_url"]
    assert e["description"] == row["summary"]


ARCHER_HTML = """
<html><body>
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif"/> Archer</h1><b>Source</b> <a href="http://paizo.com/x"><i>Advanced Player's Guide pg. 104</i></a><br />The archer is dedicated to the mastery of the bow.<br /><br /><b>Hawkeye (Ex)</b>:  At 2nd level, an archer gains a +1 bonus on Perception checks. These bonuses increase by +1 for every 4 levels beyond 2nd. This ability replaces bravery.<br /><br /><b>Trick Shot (Ex)</b>:  At 3rd level, an archer can choose a combat maneuver. This ability alters armor training.<br /><br /><b>Safe Shot (Ex)</b>:  At 9th level, an archer does not provoke. This ability replaces armor training 1 and weapon training 2.<br />
</body></html>
"""


def test_parse_archetype_features():
    feats = parse_archetype_features(ARCHER_HTML)
    assert [f["name"] for f in feats] == ["Hawkeye", "Trick Shot", "Safe Shot"]
    assert feats[0]["level"] == 2
    assert feats[0]["replaces"] == ["bravery"]
    assert feats[0]["alters"] == []
    assert feats[0]["text"].startswith("At 2nd level")
    assert feats[1]["alters"] == ["armor training"]
    assert feats[2]["replaces"] == ["armor training 1", "weapon training 2"]
    assert feats[2]["level"] == 9


def test_parse_archetype_features_no_level():
    html = ARCHER_HTML.replace("At 2nd level, an archer", "An archer")
    feats = parse_archetype_features(html)
    assert feats[0]["level"] is None
