"""Test per tools/import_reference.py — parser su fixture HTML inline (no rete)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_reference import (SKILL_HEADER_RE, _class_skill_matches,
                                    parse_abilities, parse_class,
                                    parse_equipment_table, parse_item_source,
                                    parse_race, parse_skill, parse_traits,
                                    source_id, slug)
from tools.import_reference import extract_prerequisites


def test_extract_prerequisites():
    d1 = "You increase the damage of your attacks.\n\nPrerequisites: Str 13, base attack bonus +1.\n\nBenefit: You can choose to take a -1 penalty."
    assert extract_prerequisites(d1) == ["Str 13", "base attack bonus +1"]
    d2 = "Benefit: You gain a +2 bonus.\n\nNormal: Without this feat, nothing."
    assert extract_prerequisites(d2) == []
    d3 = "Prerequisite: Dex 15, Nimble Moves, base attack bonus +7.\n\nBenefit: X."
    assert extract_prerequisites(d3) == ["Dex 15", "Nimble Moves", "base attack bonus +7"]
    print("OK: extract_prerequisites fixture")

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


# Fixture ricalcate sul markup REALE aonprd delle esotiche (cache 2026-07-19):
# heading h1 '<Razza> Racial Traits', righe flat <b> separate da <br/>, ultimo
# bold (Languages) subito prima dell'heading successivo senza <br/> interposto.

GOBLIN_HTML = """
<html><body>
<h1 class="title">Goblin Racial Traits</h1><b>+4 Dexterity, –2 Strength, –2 Charisma</b>: Goblins are fast but weak, and they're unpleasant to be around.<br /> <b>Small</b>: Goblins are Small and gain a +1 size bonus to their AC.<br /> <b>Normal Speed</b>: Goblins are fast for their size, and have a base speed of 30 feet.<br /> <b>Darkvision</b>: Goblins can see in the dark up to 60 feet.<br /> <b>Languages</b>: Goblins begin play speaking Goblin. Goblins with high Intelligence scores can choose from the following languages: Common, Draconic, and Orc<h1 class="title">Subraces</h1><h3 class="framing">Oversized Goblins</h3><p>flavor</p>
</body></html>
"""


def test_parse_race_exotic_goblin():
    """Formato Goblin: heading h1 '<Razza> Racial Traits', mods +4/–2/–2,
    lista lingue SENZA punto finale prima dell'heading successivo."""
    entry = parse_race(GOBLIN_HTML, "Goblin")
    mech = entry["mechanics"]
    assert mech["ability_mods"] == {"dex": 4, "str": -2, "cha": -2}
    assert mech["size"] == "Small"
    assert mech["speed"] == 30
    assert any(t["name"] == "Darkvision" for t in mech["traits"])
    assert mech["languages"]["auto"] == ["Goblin"]
    # Il dettaglio dell'ultimo bold si ferma all'heading 'Subraces':
    # senza stop sugli heading il bonus finale sarebbe 'OrcSubraces ...'.
    assert mech["languages"]["bonus"] == ["Common", "Draconic", "Orc"]
    print("OK: parse_race exotic goblin")


KASATHA_HTML = """
<html><body>
<h1 class="title">Kasatha Racial Traits</h1><b>+2 Dexterity, +2 Wisdom</b>: Kasathas are nimble and perceptive.<br /> <b>Medium</b>: Kasathas are Medium creatures.<br /> <b>Normal Speed</b>: Kasathas have a base speed of 30 feet.<br /> <b>Multi-Armed</b>: Kasathas have four arms.<br /> <b>Languages</b>: Kasathas speak Common and Kasatha. Kasathas with high Intelligence scores can choose from the following: Dwarven, Draconic, Gnoll, Orc, and Sphinx.<h1 class="title">Kasatha Alternate Racial Traits</h1>
</body></html>
"""


def test_parse_race_exotic_kasatha():
    """Formato Kasatha: mods senza penalita', lingue con 'speak' (non
    'begin play speaking') e bonus da 'choose from the following:'."""
    entry = parse_race(KASATHA_HTML, "Kasatha")
    mech = entry["mechanics"]
    assert mech["ability_mods"] == {"dex": 2, "wis": 2}
    assert mech["size"] == "Medium"
    assert mech["speed"] == 30
    assert any(t["name"] == "Multi-Armed" for t in mech["traits"])
    assert mech["languages"]["auto"] == ["Common", "Kasatha"]
    assert mech["languages"]["bonus"] == ["Dwarven", "Draconic", "Gnoll", "Orc", "Sphinx"]
    print("OK: parse_race exotic kasatha")


STRIX_HTML = """
<html><body>
<h1 class="title">Strix Racial Traits</h1><b>+2 Dexterity, –2 Charisma</b>: Strix are swift but aloof.<br /> <b>Medium</b>: Strix are Medium creatures.<br /> <b>Normal Speed</b>: Strix have a base speed of 30 feet.<br /> <b>Flight</b>: Strix have a fly speed of 60 feet with average maneuverability.<br /> <b>Languages</b>: Strix begin play speaking Strix. Those with high Intelligence scores can choose any of the following languages: Auran, Azlanti, Common, Draconic, and Infernal.<h1 class="title">Strix Alternate Racial Traits</h1>
</body></html>
"""


def test_parse_race_exotic_strix():
    """Formato Strix: mods a due voci, bonus lingue da 'choose any of ...'."""
    entry = parse_race(STRIX_HTML, "Strix")
    mech = entry["mechanics"]
    assert mech["ability_mods"] == {"dex": 2, "cha": -2}
    assert mech["size"] == "Medium"
    assert mech["speed"] == 30
    assert any(t["name"] == "Flight" for t in mech["traits"])
    assert mech["languages"]["auto"] == ["Strix"]
    assert mech["languages"]["bonus"] == ["Auran", "Azlanti", "Common", "Draconic", "Infernal"]
    print("OK: parse_race exotic strix")


CLASS_HTML = """
<html><body>
<h2>Barbarian</h2>
<p><b>Hit Die</b>: d12.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The barbarian's class skills are Acrobatics (Dex), Climb (Str), Intimidate (Cha), and Perception (Wis).</p>
<p><b>Skill Points per Level</b>: 4 + Int modifier.</p>
<table><tr><th>Level</th><th>Base Attack Bonus</th><th>Fort Save</th><th>Ref Save</th><th>Will Save</th><th>Special</th><th>0</th><th>1st</th><th>Unarmed Damage</th></tr>
<tr><td colspan="6"></td><td colspan="2"><b>Spells Per Day</b></td></tr>
<tr><td>1st</td><td>+1</td><td>+2</td><td>+0</td><td>+0</td><td>Fast movement, rage</td><td>3</td><td>1</td><td>1d6</td></tr>
<tr><td>2nd</td><td>+2</td><td>+3</td><td>+0</td><td>+0</td><td>Rage power, uncanny dodge</td><td>4</td><td>2</td><td>1d6</td></tr></table>
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
    assert lvl1["spells_per_day"] == {"0": "3", "1st": "1"}
    assert "Unarmed Damage" in lvl1.get("extra_progression", {})
    assert "Unarmed Damage" not in lvl1.get("spells_per_day", {})
    assert mech["progression"][1]["level"] == 2
    assert entry["source_id"] == "pfrpg_core:barbarian"
    print("OK: parse_class fixture")


# Fixture ricalcate sul markup REALE aonprd delle classi non-core (cache
# 2026-07-19, data/reference/aon_cache): stesso stile di CLASS_HTML, righe
# lv1/lv2 campione e metadati nella forma reale ('Skill Points at each Level').

ALCHEMIST_HTML = """
<html><body>
<h2>Alchemist</h2>
<p><b>Hit Die</b>: d8.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The alchemist's class skills are Appraise (Int), Craft (any) (Int), Disable Device (Dex), Fly (Dex), Heal (Wis), Knowledge (arcana) (Int), Knowledge (nature) (Int), Perception (Wis), Profession (Wis), Sleight of Hand (Dex), Spellcraft (Int), Survival (Wis), and Use Magic Device (Cha).</p>
<p><b>Skill Points at each Level</b>: 4 + Int modifier.</p>
<table><tr><td colspan="6">&nbsp;</td><td colspan="6"><b>Spells Per Day</b></td></tr>
<tr><td><b>Level</b></td><td><b>Base Attack Bonus</b></td><td><b>Fort Save</b></td><td><b>Ref Save</b></td><td><b>Will Save</b></td><td><b>Special</b></td><td><b>1st</b></td><td><b>2nd</b></td><td><b>3rd</b></td><td><b>4th</b></td><td><b>5th</b></td><td><b>6th</b></td></tr>
<tr><td>1st</td><td>+0</td><td>+2</td><td>+2</td><td>+0</td><td>Alchemy, bomb 1d6, Brew Potion, mutagen, Throw Anything</td><td>1</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td>2nd</td><td>+1</td><td>+3</td><td>+3</td><td>+0</td><td>Discovery, poison resistance +2, poison use</td><td>2</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr></table>
</body></html>
"""


def test_parse_class_alchemist_extracts():
    """Formato Alchemist (APG): riga-gruppo colspan sopra l'header, colonne
    1st-6th che riportano ESTRATTI importati in spells_per_day (semantica
    dichiarata: estratti ~= livelli incantesimo, non incantesimi RAW).
    La class skill reale 'Craft (any) (Int)' e' normalizzata a 'Craft'."""
    entry = parse_class(ALCHEMIST_HTML, "Alchemist")
    mech = entry["mechanics"]
    assert mech["hd"] == "d8"
    assert mech["skill_points_per_level"] == 4
    assert "Craft" in mech["class_skills"]
    assert "Craft (any)" not in mech["class_skills"]
    lvl1 = mech["progression"][0]
    assert (lvl1["bab"], lvl1["fort"], lvl1["ref"], lvl1["will"]) == (0, 2, 2, 0)
    # Le celle '-' sono saltate: resta solo il cerchio con slot.
    assert lvl1["spells_per_day"] == {"1st": "1"}
    assert "bomb 1d6" in lvl1["special"]
    assert mech["progression"][1]["spells_per_day"] == {"1st": "2"}
    assert entry["source"] == "Advanced Player's Guide"
    assert entry["tags"] == ["class", "base"]
    assert entry["source_id"] == "pfrpg_core:alchemist"
    print("OK: parse_class alchemist extracts")


BRAWLER_HTML = """
<html><body>
<h2>Brawler</h2>
<p><b>Hit Die</b>: d10.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The brawler's class skills are Acrobatics (Dex), Climb (Str), Craft (Int), Escape Artist (Dex), Handle Animal (Cha), Intimidate (Cha), Knowledge (dungeoneering) (Int), Knowledge (local) (Int), Perception (Wis), Profession (Wis), Ride (Dex), Sense Motive (Wis), and Swim (Str).</p>
<p><b>Skill Points at each Level</b>: 4 + Int modifier.</p>
<table><tr><td><b>Level</b></td><td><b>Base Attack Bonus</b></td><td><b>Fort Save</b></td><td><b>Ref Save</b></td><td><b>Will Save</b></td><td><b>Special</b></td><td><b>Unarmed Damage</b></td></tr>
<tr><td>1st</td><td>+1</td><td>+2</td><td>+2</td><td>+0</td><td>Brawler's cunning, martial flexibility, martial training, unarmed strike</td><td>1d6</td></tr>
<tr><td>2nd</td><td>+2</td><td>+3</td><td>+3</td><td>+0</td><td>Bonus combat feat, brawler's flurry (Two-Weapon Fighting)</td><td>1d6</td></tr></table>
</body></html>
"""


def test_parse_class_brawler_unarmed_damage():
    """Formato Brawler (ACG, tag hybrid): nessuna riga-gruppo, colonna
    'Unarmed Damage' -> extra_progression, MAI in spells_per_day."""
    entry = parse_class(BRAWLER_HTML, "Brawler")
    mech = entry["mechanics"]
    assert mech["hd"] == "d10"
    assert mech["skill_points_per_level"] == 4
    lvl1 = mech["progression"][0]
    assert (lvl1["bab"], lvl1["fort"], lvl1["ref"], lvl1["will"]) == (1, 2, 2, 0)
    assert lvl1["extra_progression"] == {"Unarmed Damage": "1d6"}
    assert "spells_per_day" not in lvl1
    assert "Unarmed Damage" not in lvl1.get("spells_per_day", {})
    assert lvl1["special"] == ["Brawler's cunning", "martial flexibility",
                               "martial training", "unarmed strike"]
    assert "brawler's flurry (Two-Weapon Fighting)" in mech["progression"][1]["special"]
    assert entry["source"] == "Advanced Class Guide"
    assert entry["tags"] == ["class", "hybrid"]
    assert entry["source_id"] == "pfrpg_core:brawler"
    print("OK: parse_class brawler unarmed damage")


WITCH_HTML = """
<html><body>
<h2>Witch</h2>
<p><b>Hit Die</b>: d6.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<h3>Class Skills</h3>
<p>The witch's class skills are Craft (Int), Fly (Dex), Heal (Wis), Intimidate (Cha), Knowledge (arcana) (Int), Knowledge (history) (Int), Knowledge (nature) (Int), Knowledge (planes) (Int), Profession (Wis), Spellcraft (Int), and Use Magic Device (Cha).</p>
<p><b>Skill Points at each Level</b>: 2 + Int modifier.</p>
<table><tr><td colspan="6">&nbsp;</td><td colspan="10"><b>Spells Per Day</b></td></tr>
<tr><td><b>Level</b></td><td><b>Base Attack Bonus</b></td><td><b>Fort Save</b></td><td><b>Ref Save</b></td><td><b>Will Save</b></td><td><b>Special</b></td><td><b>0</b></td><td><b>1st</b></td><td><b>2nd</b></td><td><b>3rd</b></td><td><b>4th</b></td><td><b>5th</b></td><td><b>6th</b></td><td><b>7th</b></td><td><b>8th</b></td><td><b>9th</b></td></tr>
<tr><td>1st</td><td>+0</td><td>+0</td><td>+0</td><td>+2</td><td>Cantrips, hex, witch’s familiar</td><td>3</td><td>1</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td>2nd</td><td>+1</td><td>+0</td><td>+0</td><td>+3</td><td>Hex</td><td>4</td><td>2</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr></table>
</body></html>
"""


def test_parse_class_witch_cantrips_column():
    """Formato Witch (APG full caster): riga-gruppo + colonna cerchio '0'
    (cantrips) in spells_per_day; apostrofo tipografico reale U+2019 nello
    special ('witch’s familiar')."""
    entry = parse_class(WITCH_HTML, "Witch")
    mech = entry["mechanics"]
    assert mech["hd"] == "d6"
    assert mech["skill_points_per_level"] == 2
    lvl1 = mech["progression"][0]
    assert (lvl1["bab"], lvl1["fort"], lvl1["ref"], lvl1["will"]) == (0, 0, 0, 2)
    assert lvl1["spells_per_day"] == {"0": "3", "1st": "1"}
    assert "witch’s familiar" in lvl1["special"]
    lvl2 = mech["progression"][1]
    assert lvl2["will"] == 3
    assert lvl2["spells_per_day"] == {"0": "4", "1st": "2"}
    assert entry["source"] == "Advanced Player's Guide"
    assert entry["tags"] == ["class", "base"]
    assert entry["source_id"] == "pfrpg_core:witch"
    print("OK: parse_class witch cantrips column")


PROFICIENCIES_HTML = """
<html><body>
<h2>Alchemist</h2>
<p><b>Hit Die</b>: d8.</p>
<p><b>Starting Wealth</b>: 3d6 x 10 gp (average 105 gp).</p>
<p><b>Weapon and Armor Proficiency</b>: Alchemists are proficient with all simple weapons and bombs. They are also proficient with light armor, but not with shields.</p>
<p><b>Alchemy (Su)</b>: Alchemists are masters of alchemical substances.</p>
<p><b>Skill Points at each Level</b>: 4 + Int modifier.</p>
<table><tr><td><b>Level</b></td><td><b>Base Attack Bonus</b></td><td><b>Fort Save</b></td><td><b>Ref Save</b></td><td><b>Will Save</b></td><td><b>Special</b></td></tr>
<tr><td>1st</td><td>+0</td><td>+2</td><td>+2</td><td>+0</td><td>Alchemy</td></tr></table>
</body></html>
"""


def test_parse_class_proficiencies_two_sentences():
    """Blocco proficiency a DUE frasi (armi. armature.): entrambe finiscono
    nel campo (forma testuale preservata, punto finale rimosso come nella
    forma pre-fix); l'etichetta della sezione successiva ('Alchemy (Su) : ...')
    chiude il blocco e resta fuori. Sub-caso Witch: anche le frasi su arcane
    spell failure ('Armor interferes with ...') chiudono il blocco (NON sono
    proficiency)."""
    entry = parse_class(PROFICIENCIES_HTML, "Alchemist")
    prof = entry["mechanics"]["proficiencies"]
    assert "all simple weapons and bombs" in prof
    assert "light armor, but not with shields" in prof
    assert prof.endswith("shields")
    assert "Alchemy" not in prof
    html = ("<html><body><p><b>Weapon and Armor Proficiency</b>: Witches are "
            "proficient with all simple weapons. They are not proficient with "
            "any type of armor or shield. Armor interferes with a witch's "
            "gestures, which can cause her spells to fail.</p></body></html>")
    prof = parse_class(html, "Witch")["mechanics"]["proficiencies"]
    assert prof == ("Witches are proficient with all simple weapons. "
                    "They are not proficient with any type of armor or shield")
    print("OK: parse_class proficiencies two sentences")


def test_skill_header_regex():
    name, key, trained, acp = SKILL_HEADER_RE("Disable Device (Int; Trained Only)")
    assert (name, key, trained, acp) == ("Disable Device", "int", True, False)
    name, key, trained, acp = SKILL_HEADER_RE("Acrobatics (Dex; Armor Check Penalty)")
    assert (name, key, trained, acp) == ("Acrobatics", "dex", False, True)
    name, key, trained, acp = SKILL_HEADER_RE("Perception (Wis)")
    assert (name, key, trained, acp) == ("Perception", "wis", False, False)


def test_parse_skill():
    html = "<html><body><h2>Acrobatics (Dex; Armor Check Penalty)</h2><p>You can keep your balance.</p></body></html>"
    entry = parse_skill(html, "Acrobatics")
    assert entry["mechanics"] == {"key_ability": "dex", "trained_only": False,
                                  "armor_check_penalty": True, "class_skills_of": []}
    print("OK: parse_skill fixture")


def test_class_skill_matches():
    assert _class_skill_matches("Knowledge (Arcana)", "Knowledge (arcana)")
    assert _class_skill_matches("Knowledge (Arcana)", "Knowledge (all)")
    assert _class_skill_matches("Perception", "Perception")
    assert not _class_skill_matches("Perception", "knowledge (all)")
    assert not _class_skill_matches("Spellcraft", "Craft")
    print("OK: class_skill_matches")


WEAPONS_HTML = """
<html><body><table>
<tr><th>Name</th><th>Cost</th><th>Dmg (S)</th><th>Dmg (M)</th><th>Critical</th><th>Range</th><th>Weight</th><th>Type</th><th>Special</th></tr>
<tr><td><a href="EquipmentWeaponsDisplay.aspx?ItemName=Longsword">Longsword</a></td><td>15 gp</td><td>1d6</td><td>1d8</td><td>19-20/x2</td><td>-</td><td>4 lbs.</td><td>S</td><td>-</td></tr>
<tr><td>Shortbow</td><td>30 gp</td><td>1d4</td><td>1d6</td><td>x3</td><td>60 ft.</td><td>2 lbs.</td><td>P</td><td>-</td></tr>
<tr><td><a href="EquipmentWeaponsDisplay.aspx?ItemName=Battle aspergillum">Battle aspergillum</a></td><td>5 gp</td><td>1d4</td><td>1d6</td><td>x2</td><td>-</td><td>4 lbs.</td><td>B</td><td>monk</td></tr>
</table></body></html>
"""


def test_parse_equipment_table():
    entries = parse_equipment_table(WEAPONS_HTML, "weapon", "simple")
    ls = entries[0]
    assert ls["mechanics"]["cost"] == "15 gp"
    assert ls["mechanics"]["dmg_m"] == "1d8"
    assert ls["mechanics"]["critical"] == "19-20/x2"
    assert ls["mechanics"]["weight"] == "4 lbs."
    assert ls["tags"] == ["equipment", "weapon", "simple"]
    # Detail URL dal link nel nome; senza link fallback al generico.
    assert ls["reference_urls"] == [
        "https://aonprd.com/EquipmentWeaponsDisplay.aspx?ItemName=Longsword",
        "https://aonprd.com/Equipment.aspx"]
    assert entries[1]["reference_urls"] == ["https://aonprd.com/Equipment.aspx"]
    assert entries[1]["mechanics"]["range"] == "60 ft."
    # Spazi negli href AoN: URL-encode nel detail URL.
    assert entries[2]["reference_urls"][0] == (
        "https://aonprd.com/EquipmentWeaponsDisplay.aspx?ItemName=Battle%20aspergillum")
    print("OK: parse_equipment_table fixture")


def test_parse_item_source():
    html = "<html><body><h2>Klar</h2><p>Source Ultimate Equipment pg. 24</p></body></html>"
    assert parse_item_source(html) == "Ultimate Equipment"
    html2 = "<html><body><p>Source PRPG Core Rulebook pg. 141</p></body></html>"
    assert parse_item_source(html2) == "PFRPG Core"
    # Piu' fonti: si preferisce il Core Rulebook (le altre sono ristampe).
    html3 = "<html><body><p>Source Ultimate Equipment pg. 18, PRPG Core Rulebook pg. 142</p></body></html>"
    assert parse_item_source(html3) == "PFRPG Core"
    print("OK: parse_item_source fixture")


TRAITS_HTML = """
<html><body>
<h3><a href="TraitDisplay.aspx?ItemName=Reactionary">Reactionary</a></h3>
<p><b>Source</b> Ultimate Campaign pg. 63</p>
<p>You were bullied as a child. You gain a +2 trait bonus on initiative checks.</p>
<h3><a href="TraitDisplay.aspx?ItemName=Indomitable+Faith">Indomitable Faith</a></h3>
<p><b>Source</b> Ultimate Campaign pg. 60</p>
<p><b>Requirement(s)</b> None</p>
<p>You gain a +1 trait bonus on Will saves.</p>
</body></html>
"""


def test_parse_traits():
    entries = parse_traits(TRAITS_HTML, "Basic (Combat)")
    assert entries[0]["name"] == "Reactionary"
    assert entries[0]["mechanics"]["category"] == "Basic (Combat)"
    assert "initiative" in entries[0]["description"]
    assert entries[1]["name"] == "Indomitable Faith"
    assert len(entries) == 2
    print("OK: parse_traits fixture")


def test_parse_traits_strips_suggested_characters():
    html = ("<html><body>"
            "<h3><a href=\"TraitDisplay.aspx?ItemName=Inspiring\">Inspiring</a></h3>"
            "<p><b>Source</b> Ultimate Campaign pg. 61</p>"
            "<p>You gain a +1 trait bonus on Diplomacy checks. Suggested Characters : Iomedaeans, Chelaxians.</p>"
            "</body></html>")
    entries = parse_traits(html, "Basic (Social)")
    assert "Suggested Characters" not in entries[0]["description"]
    assert "Iomedaeans" not in entries[0]["description"]
    assert "Diplomacy" in entries[0]["description"]
    print("OK: traits strip suggested characters")


def test_trait_pi_supplement():
    from tools.import_reference import _trait_pi_hits
    entry = {"name": "Acadamae Neophyte", "description": "You studied at the Acadamae of Korvosa.",
             "prerequisites": [], "source": "Ultimate Campaign"}
    assert _trait_pi_hits(entry)
    clean_entry = {"name": "Reactionary", "description": "+2 trait bonus on initiative checks.",
                   "prerequisites": [], "source": "Ultimate Campaign"}
    assert not _trait_pi_hits(clean_entry)
    society = {"name": "Pathfinder's Focus", "description": "+1 on saves.",
               "prerequisites": [], "source": "Pathfinder Society Primer"}
    assert _trait_pi_hits(society)
    print("OK: trait PI supplement")


def test_trait_pi_supplement_demonyms():
    from tools.import_reference import _trait_pi_hits
    prereq = {"name": "Hill Fighter", "description": "+1 trait bonus on attacks.",
              "prerequisites": ["Sargavan"], "source": "Sargava, the Lost Colony"}
    assert _trait_pi_hits(prereq)
    desc = {"name": "Obari Veteran", "description": "Garundi and Vudrani traditions.",
            "prerequisites": [], "source": "Ultimate Campaign"}
    assert _trait_pi_hits(desc)
    print("OK: trait PI supplement demonyms")


def test_parse_traits_comma_source():
    html = ("<html><body>"
            "<h3><a href=\"TraitDisplay.aspx?ItemName=Hill+Fighter\">Hill Fighter</a></h3>"
            "<p><b>Source</b> Sargava, the Lost Colony pg. 12</p>"
            "<p>You gain a +1 trait bonus on attacks from higher ground.</p>"
            "</body></html>")
    entries = parse_traits(html, "Basic (Combat)")
    assert entries[0]["source"] == "Sargava, the Lost Colony"
    assert entries[0]["source_id"].startswith("sargava_the_lost_colony:")
    print("OK: traits comma source")


from tools.import_reference import parse_feats_index, split_prereq_string

FEATS_INDEX_HTML = """
<html><body><table>
<tr><th>Name</th><th>Prerequisite</th><th>Description</th></tr>
<tr><td>Power Attack*</td><td>Str 13, base attack bonus +1</td><td>You hit harder.</td></tr>
<tr><td>Nimble Moves⊤</td><td>Dex 13, dodge, Mobility</td><td>Move 5 ft.</td></tr>
</table></body></html>
"""


def test_parse_feats_index():
    lookup = parse_feats_index(FEATS_INDEX_HTML)
    assert lookup["powerattack"] == "Str 13, base attack bonus +1"
    assert lookup["nimblemoves"] == "Dex 13, dodge, Mobility"


def test_split_prereq_string():
    assert split_prereq_string("Str 13, base attack bonus +1") == ["Str 13", "base attack bonus +1"]
    assert split_prereq_string("Int 13, Spell Focus (illusion), wizard level 3rd") == ["Int 13", "Spell Focus (illusion)", "wizard level 3rd"]
    assert split_prereq_string("") == []
    print("OK: feats index + split")


from tools.import_reference import clean_existing_prerequisites


def test_clean_existing_prerequisites():
    entry = {"name": "Improved Initiative", "prerequisites": ["Improved Initiative."]}
    assert clean_existing_prerequisites(entry) == []
    entry2 = {"name": "Power Attack", "prerequisites": ["Strength 13", "base attack bonus +1."]}
    assert clean_existing_prerequisites(entry2) == ["Strength 13", "base attack bonus +1"]
    entry3 = {"name": "Dodge", "prerequisites": ["Dexterity 13"]}
    assert clean_existing_prerequisites(entry3) == ["Dexterity 13"]
    print("OK: clean existing prerequisites")
