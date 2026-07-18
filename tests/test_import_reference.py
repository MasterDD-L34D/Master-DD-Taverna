"""Test per tools/import_reference.py — parser su fixture HTML inline (no rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import parse_abilities, parse_class, parse_race, source_id, slug

ABILITIES_HTML = """
<html><body>
<table><tr><th>Score</th><th>Points</th></tr>
<tr><td>7</td><td>-4</td></tr><tr><td>10</td><td>0</td></tr>
<tr><td>14</td><td>5</td></tr><tr><td>18</td><td>17</td></tr></table>
<table><tr><th>Campaign Type</th><th>Points</th></tr>
<tr><td>Low Fantasy</td><td>10</td></tr><tr><td>Standard Fantasy</td><td>15</td></tr>
<tr><td>High Fantasy</td><td>20</td></tr><tr><td>Epic Fantasy</td><td>25</td></tr></table>
</body></html>
"""


def test_slug_and_source_id():
    assert slug("Half-Elf (Standard)") == "half_elf_standard"
    assert source_id("pfrpg_core", "Power Attack") == "pfrpg_core:power_attack"


def test_parse_abilities():
    entries = parse_abilities(ABILITIES_HTML)
    costs = {e["name"]: e["mechanics"]["cost"] for e in entries if e["mechanics"]["kind"] == "ability_cost"}
    budget = {e["name"]: e["mechanics"]["points"] for e in entries if e["mechanics"]["kind"] == "campaign_budget"}
    assert costs == {"Score 7": -4, "Score 10": 0, "Score 14": 5, "Score 18": 17}
    assert budget == {"Low Fantasy": 10, "Standard Fantasy": 15, "High Fantasy": 20, "Epic Fantasy": 25}
    assert all(e["source_id"].startswith("pfrpg_core:") for e in entries)
    print("OK: parse_abilities fixture")


RACE_HTML = """
<html><body>
<h2>Dwarf</h2>
<h3>Racial Traits</h3>
<p><b>+2 Constitution, +2 Wisdom, –2 Charisma:</b> Dwarves are both tough and wise.</p>
<p><b>Medium</b>: Dwarves are Medium creatures.</p>
<p><b>Slow and Steady</b>: Dwarves have a base speed of 20 feet.</p>
<p><b>Darkvision</b>: Dwarves can see in the dark up to 60 feet.</p>
<p><b>Defensive Training</b>: Dwarves gain a +4 dodge bonus to AC against giants.</p>
<p><b>Languages</b>: Dwarves begin play speaking Common and Dwarven. Dwarves with high Intelligence can choose from Giant, Gnome, Goblin, Orc, Terran, and Undercommon.</p>
</body></html>
"""


def test_parse_race():
    entry = parse_race(RACE_HTML, "Dwarf")
    mech = entry["mechanics"]
    assert mech["ability_mods"] == {"con": 2, "wis": 2, "cha": -2}
    assert mech["size"] == "Medium"
    assert mech["speed"] == 20
    assert any(t["name"] == "Darkvision" for t in mech["traits"])
    assert mech["languages"]["auto"] == ["Common", "Dwarven"]
    assert "Gnome" in mech["languages"]["bonus"]
    assert entry["source_id"] == "pfrpg_core:dwarf"
    assert "Darkvision" in entry["description"]
    print("OK: parse_race fixture")


def test_parse_race_any_bonus():
    html = ("<html><body><h3>Racial Traits</h3>"
            "<p><b>+2 to One Ability Score</b>: Humans get a bonus feat.</p></body></html>")
    entry = parse_race(html, "Human")
    assert entry["mechanics"]["ability_mods"] == {"any": 2}
    print("OK: parse_race any-bonus")


def test_race_scoping_fail_closed():
    html = "<html><body><h1>Subraces</h1><p><b>Deep Delver</b>: text</p></body></html>"
    entry = parse_race(html, "Dwarf")
    assert entry["mechanics"]["traits"] == []
    print("OK: race scoping fail-closed")


CLASS_HTML = """
<html><body>
<h2>Barbarian</h2>
<p><b>Hit Die</b>: d12.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The barbarian's class skills are Acrobatics (Dex), Climb (Str), Intimidate (Cha), and Perception (Wis).</p>
<p><b>Skill Points per Level</b>: 4 + Int modifier.</p>
<table><tr><th>Level</th><th>Base Attack Bonus</th><th>Fort Save</th><th>Ref Save</th><th>Will Save</th><th>Special</th></tr>
<tr><td>1st</td><td>+1</td><td>+2</td><td>+0</td><td>+0</td><td>Fast movement, rage</td></tr>
<tr><td>2nd</td><td>+2</td><td>+3</td><td>+0</td><td>+0</td><td>Rage power, uncanny dodge</td></tr></table>
</body></html>
"""


def test_parse_class():
    entry = parse_class(CLASS_HTML, "Barbarian")
    mech = entry["mechanics"]
    assert mech["hd"] == "d12"
    assert mech["skill_points_per_level"] == 4
    assert "Acrobatics" in mech["class_skills"] and "Perception" in mech["class_skills"]
    lvl1 = mech["progression"][0]
    assert lvl1["level"] == 1 and lvl1["bab"] == 1 and lvl1["fort"] == 2 and lvl1["ref"] == 0
    assert "rage" in lvl1["special"]
    assert mech["progression"][1]["level"] == 2
    assert entry["source_id"] == "pfrpg_core:barbarian"
    print("OK: parse_class fixture")
