"""Test per tools/enrich_equipment_descriptions.py — description flavor da pagine dettaglio AoN."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.enrich_equipment_descriptions import (
    enrich_entry,
    parse_equipment_description,
)

CHAINMAIL_HTML = """
<html><body>
<span id="MainContent_DataListTypes_LabelName_0"><h1 class="title">Chainmail</h1><b>Source</b> <a href="http://paizo.com/x"><i>PRPG Core Rulebook pg. 151</i></a><h3 class="framing">Statistics</h3><b>Cost</b> 150 gp <b>Weight</b> 40 lbs.<br /><b>Armor Bonus</b> +6; <b>Max Dex Bonus</b> +2; <b>Armor Check Penalty</b> -5<br /><b>Arcane Spell Failure Chance</b> 30%; <b>Speed</b> 20 ft./15 ft.<h3 class="framing">Description</h3>Unlike a chain shirt, which covers only the chest, chainmail protects the wearer with a complete mesh of chain links that cover the torso and arms. The suit includes gauntlets.</span>
</body></html>
"""


def test_parse_equipment_description():
    text = parse_equipment_description(CHAINMAIL_HTML)
    assert text.startswith("Unlike a chain shirt")
    assert "gauntlets" in text
    assert "Statistics" not in text and "150 gp" not in text


def test_parse_equipment_description_missing_section():
    assert parse_equipment_description("<html><body><p>niente</p></body></html>") == ""


def test_enrich_entry_appends_flavor_once():
    entry = {
        "name": "Chainmail",
        "description": "Chainmail (armor, medium), costo 150 gp, peso 40 lbs.",
    }
    out = enrich_entry(entry, "Unlike a chain shirt, it covers the torso.")
    assert out["description"] == (
        "Chainmail (armor, medium), costo 150 gp, peso 40 lbs.\n\n"
        "Unlike a chain shirt, it covers the torso."
    )
    # idempotenza: secondo passaggio non raddoppia
    out2 = enrich_entry(out, "Unlike a chain shirt, it covers the torso.")
    assert out2["description"] == out["description"]


def test_enrich_entry_empty_flavor_is_noop():
    entry = {"name": "X", "description": "X (armor, light), costo 5 gp."}
    assert enrich_entry(entry, "")["description"] == entry["description"]
