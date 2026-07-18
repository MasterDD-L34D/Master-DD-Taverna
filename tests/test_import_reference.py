"""Test per tools/import_reference.py — parser su fixture HTML inline (no rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import parse_abilities, source_id, slug

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
