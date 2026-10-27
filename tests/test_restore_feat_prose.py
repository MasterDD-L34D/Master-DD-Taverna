"""Test per tools/restore_feat_prose.py — ripristino prosa da FeatDisplay AoN."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.restore_feat_prose import appendix_names, apply_restore, parse_feat_page

# Markup ricalcato su FeatDisplay.aspx reale (cache Elemental Channel).
FEAT_HTML = """
<html><body>
<span id="MainContent_DataListTypes_LabelName_0"><h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Elemental Channel</h1><b>Source</b> <a href="http://paizo.com/x" class="external-link"><i>PRPG Core Rulebook pg. 122</i></a><br />Choose one elemental subtype, such as air, earth, fire, or water.<br /><br /><b>Prerequisites</b>: Channel energy class feature.<br /><br /><b>Benefit</b>: Instead of its normal effect, you can choose to heal or harm outsiders of your chosen elemental subtype. The amount of damage is otherwise unchanged.<br /><br /><b>Special</b>: You can gain this feat multiple times.</span>
</body></html>
"""


def test_parse_feat_page():
    p = parse_feat_page(FEAT_HTML)
    assert p["name"] == "Elemental Channel"
    assert p["source"] == "PRPG Core Rulebook"
    assert (
        p["flavor"]
        == "Choose one elemental subtype, such as air, earth, fire, or water."
    )
    assert p["prerequisites"] == ["Channel energy class feature"]
    assert p["benefit"].startswith("Instead of its normal effect")
    assert "multiple times" not in p["benefit"]  # Special escluso


def test_apply_restore_entry_shape():
    entry = {
        "name": "Elemental Channel",
        "source": "PRPG Core Rulebook",
        "prerequisites": ["old corrupted"],
        "references": ["Archives of a deity of magic: Elemental Channel"],
        "description": "Choose one ea bardental subtype...",
        "tags": ["PRPG Core Rulebook"],
        "source_id": "prpg_core_rulebook:elemental_channel",
    }
    p = parse_feat_page(FEAT_HTML)
    out = apply_restore(entry, p)
    assert out["description"] == (
        "Choose one elemental subtype, such as air, earth, fire, or water.\n\n"
        + p["benefit"]
    )
    assert out["prerequisites"] == ["Channel energy class feature"]
    assert out["references"] == ["Pathfinder PRD: Elemental Channel"]
    assert out["source"] == "PRPG Core Rulebook"  # invariato
    assert out["source_id"] == "prpg_core_rulebook:elemental_channel"  # invariato
    assert out["updated_at"]


def test_appendix_names_from_committed_report():
    names = appendix_names()
    assert len(names) == 75
    assert "Djinni Spin" in names and "Elemental Channel" not in names
