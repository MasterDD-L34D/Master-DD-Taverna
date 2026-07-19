"""Test per tools/import_spells.py — parser pagine AoN SpellDisplay + merge.

Fixture HTML inline (MAI rete): markup ridotto ma fedele alle pagine reali
`SpellDisplay.aspx?ItemName=...` (tabella MainContent_DataListTypes, span
LabelName, blocchi h1.title, sezioni h3.framing, label in <b>).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_spells import _merge_entry, _spell_pi_hits, parse_spell

# Forma reale: pagina a blocco singolo (Acid Arrow, 2026-07-19).
FIXTURE_SINGLE = """
<html><body><div id="main">
<table id="MainContent_DataListTypes"><tr><td>
<span id="MainContent_DataListTypes_LabelName_0">
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Acid Arrow</h1>
<b>Source</b> <a class="external-link" href="http://paizo.com/x"><i>PRPG Core Rulebook pg. 239</i></a><br/>
<b>School</b> <u><a href="SpellDefinitions.aspx?ID=2">conjuration</a></u> (<u><a href="SpellDefinitions.aspx?ID=13">creation</a></u>) [<u><a href="SpellDefinitions.aspx?ID=25">acid</a></u>];
<b>Level</b> arcanist 2, bloodrager 2, magus 2, sorcerer 2, wizard 2
<h3 class="framing">Casting</h3>
<b>Casting Time</b> 1 standard action<br/>
<b>Components</b> V, S, M (rhubarb leaf and an adder's stomach), F (a dart)
<h3 class="framing">Effect</h3>
<b>Range</b> long (400 ft. + 40 ft./level)<br/>
<b>Effect</b> one arrow of acid<br/>
<b>Duration</b> 1 round + 1 round per three levels<br/>
<b>Saving Throw</b> none; <b>Spell Resistance</b> no
<h3 class="framing">Description</h3>
An arrow of acid springs from your hand and speeds to its target.
</span></td></tr></table>
</div></body></html>
"""

# Forma reale: pagina multi-blocco (Fireball, 2026-07-19): blocco base +
# sezione mythic (h2.title, da escludere) + variante (secondo h1.title).
FIXTURE_MULTI = """
<html><body><div id="main">
<table id="MainContent_DataListTypes"><tr></tr><tr><td>
<span id="MainContent_DataListTypes_LabelName_1">
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Fireball</h1>
<b>Source</b> <a class="external-link" href="http://paizo.com/x"><i>PRPG Core Rulebook pg. 283</i></a><br/>
<b>School</b> <u><a href="SpellDefinitions.aspx?ID=5">evocation</a></u> [<u><a href="SpellDefinitions.aspx?ID=39">fire</a></u>];
<b>Level</b> arcanist 3, bloodrager 3, magus 3, occultist 3, sorcerer 3, wizard 3
<h3 class="framing">Casting</h3>
<b>Casting Time</b> 1 standard action<br/>
<b>Components</b> V, S, M (a ball of bat guano and sulfur)
<h3 class="framing">Effect</h3>
<b>Range</b> long (400 ft. + 40 ft./level)<br/>
<b>Area</b> 20-ft.-radius spread<br/>
<b>Duration</b> instantaneous<br/>
<b>Saving Throw</b> Reflex half; <b>Spell Resistance</b> yes
<h3 class="framing">Description</h3>
A <i>fireball</i> spell generates a searing explosion of flame.
<h2 class="title">Mythic Fireball</h2>
<b>Source</b> <i>Mythic Adventures pg. 94</i><br/>
The damage dealt increases to 1d10 points of fire damage per caster level.
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Controlled Fireball</h1>
<b>Source</b> <a class="external-link" href="http://paizo.com/y"><i>Ultimate Intrigue pg. 208</i></a><br/>
<b>School</b> <u><a href="SpellDefinitions.aspx?ID=5">evocation</a></u> [<u><a href="SpellDefinitions.aspx?ID=39">fire</a></u>, <u><a href="SpellDefinitions.aspx?ID=49">ruse</a></u>];
<b>Level</b> arcanist 4, bloodrager 4, magus 4, occultist 4, sorcerer 4, wizard 4
<h3 class="framing">Casting</h3>
<b>Casting Time</b> 1 standard action<br/>
<b>Components</b> V, S, M (a ball of bat guano and sulfur)
<h3 class="framing">Effect</h3>
<b>Range</b> long (400 ft. + 40 ft./level)<br/>
<b>Duration</b> instantaneous<br/>
<b>Saving Throw</b> Reflex half; <b>Spell Resistance</b> yes
<h3 class="framing">Description</h3>
This spell functions as <i>fireball</i>.
</span></td></tr></table>
</div></body></html>
"""


def test_parse_spell_singolo_blocco():
    entry = parse_spell(FIXTURE_SINGLE, "Acid Arrow")
    assert entry["name"] == "Acid Arrow"
    assert entry["source"] == "PRPG Core Rulebook"
    mech = entry["mechanics"]
    assert mech["school"] == "conjuration"
    assert mech["descriptors"] == ["acid"]
    assert mech["spell_level"] == {"arcanist": 2, "bloodrager": 2, "magus": 2,
                                   "sorcerer": 2, "wizard": 2}
    assert mech["casting_time"] == "1 standard action"
    assert mech["components"] == "V, S, M (rhubarb leaf and an adder's stomach), F (a dart)"
    assert mech["range"] == "long (400 ft. + 40 ft./level)"
    assert mech["duration"] == "1 round + 1 round per three levels"
    assert mech["saving_throw"] == "none"
    assert mech["spell_resistance"] == "no"


def test_parse_spell_pagina_multiblocco_sceglie_il_blocco_giusto():
    entry = parse_spell(FIXTURE_MULTI, "Fireball")
    mech = entry["mechanics"]
    assert mech["school"] == "evocation"
    assert mech["descriptors"] == ["fire"]
    # Livello 3 del blocco base, NON 4 della variante Controlled Fireball.
    assert mech["spell_level"] == {"arcanist": 3, "bloodrager": 3, "magus": 3,
                                   "occultist": 3, "sorcerer": 3, "wizard": 3}
    assert mech["saving_throw"] == "Reflex half"
    assert mech["spell_resistance"] == "yes"
    # La sezione mythic (h2.title) non deve inquinare i campi.
    assert "1d10" not in str(mech)


def test_parse_spell_variante_come_blocco_a_se():
    entry = parse_spell(FIXTURE_MULTI, "Controlled Fireball")
    mech = entry["mechanics"]
    assert mech["descriptors"] == ["fire", "ruse"]
    assert mech["spell_level"]["sorcerer"] == 4
    assert entry["source"] == "Ultimate Intrigue"


def test_parse_spell_nome_assente_ritorna_none():
    # Fail-closed: pagina senza il blocco richiesto -> None (unmatched),
    # mai il primo blocco disponibile.
    assert parse_spell(FIXTURE_SINGLE, "Fireball") is None
    assert parse_spell("<html><body>404</body></html>", "Fireball") is None


def test_merge_entry_riempie_solo_i_campi_mancanti():
    entry = {"name": "Fireball",
             "mechanics": {"school": "evocation",
                           "spell_level": {"sorcerer/wizard": 3},
                           "saving_throw": "Reflex half"}}
    parsed = {"name": "Fireball",
              "mechanics": {"school": "evocation",
                            "descriptors": ["fire"],
                            "spell_level": {"arcanist": 3, "sorcerer": 3},
                            "casting_time": "1 standard action",
                            "saving_throw": "Reflex half"}}
    changed, notes = _merge_entry(entry, parsed)
    assert changed
    mech = entry["mechanics"]
    # Mancanti riempiti da AoN.
    assert mech["descriptors"] == ["fire"]
    assert mech["casting_time"] == "1 standard action"
    # Esistenti MAI sovrascritti: spell_level resta la forma curata combinata
    # (AoN elenca le classi separate; il merge per-chiave duplicherebbe).
    assert mech["spell_level"] == {"sorcerer/wizard": 3}
    assert any("spell_level" in n for n in notes)


def test_merge_entry_senza_cambi_reali_non_tocca():
    entry = {"name": "Acid Arrow",
             "mechanics": {"school": "conjuration", "descriptors": ["acid"],
                           "spell_level": {"sorcerer/wizard": 2},
                           "saving_throw": "none"}}
    parsed = {"name": "Acid Arrow",
              "mechanics": {"school": "conjuration", "descriptors": ["acid"],
                            "spell_level": {"sorcerer": 2, "wizard": 2},
                            "saving_throw": "none"}}
    changed, _ = _merge_entry(entry, parsed)
    assert not changed


def test_spell_pi_hits_fail_closed():
    parsed = {"name": "Acid Arrow", "source": "PRPG Core Rulebook",
              "mechanics": {"school": "conjuration", "descriptors": ["acid"],
                            "components": "V, S, M (rhubarb leaf from Golarion)"}}
    hits = _spell_pi_hits(parsed)
    assert hits and any(h["term"] == "Golarion" for h in hits)
    clean_entry = {"name": "Acid Arrow", "source": "PRPG Core Rulebook",
                   "mechanics": {"school": "conjuration", "descriptors": ["acid"],
                                 "components": "V, S, M (rhubarb leaf)"}}
    assert _spell_pi_hits(clean_entry) == []


# Forma reale verificata (2026-07-19) su SpellDisplay.aspx?ItemName=Bear%27s%20Endurance:
# l'apostrofo nei titoli h1 AoN e' ASCII dritto ('), NON un'entita'
# (&#39;/&rsquo;): il match esatto con i nomi del catalogo (ASCII) funziona.
FIXTURE_APOSTROPHE = """
<html><body><div id="main">
<table id="MainContent_DataListTypes"><tr><td>
<span id="MainContent_DataListTypes_LabelName_1">
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Bear's Endurance</h1>
<b>Source</b> <a class="external-link" href="http://paizo.com/x"><i>PRPG Core Rulebook pg. 203</i></a><br/>
<b>School</b> <u><a href="SpellDefinitions.aspx?ID=8">transmutation</a></u>;
<b>Level</b> arcanist 2, cleric 2, sorcerer 2, wizard 2
<h3 class="framing">Casting</h3>
<b>Casting Time</b> 1 standard action<br/>
<b>Components</b> V, S, M/DF (a few hairs or pinch of dung from a bear)
<h3 class="framing">Effect</h3>
<b>Range</b> touch<br/>
<b>Duration</b> 1 min./level<br/>
<b>Saving Throw</b> Will negates (harmless); <b>Spell Resistance</b> yes
<h3 class="framing">Description</h3>
The affected creature gains greater vitality and stamina.
<h1 class="title"><img src="images\\PathfinderSocietySymbol.gif" title="PFS Legal"/> Bear's Endurance, Mass</h1>
<b>Source</b> <a class="external-link" href="http://paizo.com/x"><i>PRPG Core Rulebook pg. 203</i></a><br/>
<b>School</b> <u><a href="SpellDefinitions.aspx?ID=8">transmutation</a></u>;
<b>Level</b> arcanist 6, cleric 6, sorcerer 6, wizard 6
<h3 class="framing">Casting</h3>
<b>Casting Time</b> 1 standard action<br/>
<b>Components</b> V, S, M/DF (a few hairs or pinch of dung from a bear)
<h3 class="framing">Effect</h3>
<b>Range</b> close (25 ft. + 5 ft./2 levels)<br/>
<b>Duration</b> 1 min./level<br/>
<b>Saving Throw</b> Will negates (harmless); <b>Spell Resistance</b> yes
<h3 class="framing">Description</h3>
Mass bear's endurance works like bear's endurance, except it affects multiple creatures.
</span></td></tr></table>
</div></body></html>
"""


def test_parse_spell_nome_con_apostrofo():
    # Il nome del catalogo (apostrofo ASCII) matcha il blocco h1 reale AoN,
    # senza confondersi con la variante ", Mass" (match esatto, non prefisso).
    entry = parse_spell(FIXTURE_APOSTROPHE, "Bear's Endurance")
    assert entry["name"] == "Bear's Endurance"
    assert entry["mechanics"]["school"] == "transmutation"
    assert entry["mechanics"]["spell_level"]["cleric"] == 2
    assert entry["mechanics"]["saving_throw"] == "Will negates (harmless)"
    mass = parse_spell(FIXTURE_APOSTROPHE, "Bear's Endurance, Mass")
    assert mass["mechanics"]["spell_level"]["cleric"] == 6
