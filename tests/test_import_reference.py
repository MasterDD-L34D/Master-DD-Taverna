"""Test per tools/import_reference.py — parser su fixture HTML inline (no rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import parse_abilities, parse_race, source_id, slug

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
