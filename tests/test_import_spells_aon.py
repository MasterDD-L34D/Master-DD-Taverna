"""Test per tools/import_spells_aon.py -- incantesimi mancanti da AoN (2026-11-01).

import_spells.py arricchisce le voci esistenti ma non ne aggiunge: il
censimento del 2026-11-01 ha trovato ~200 incantesimi OGL assenti.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_spells_aon import missing_spells, spell_description, spell_entry

# Forma reale di SpellDisplay (v. docstring di import_spells.py): blocco in
# <table id="MainContent_DataListTypes">, campi in <b>, sezioni h3.framing,
# varianti in un altro h1.title che chiude il blocco.
PAGE = """
<table id="MainContent_DataListTypes"><tr><td><span>
<h1 class="title">Blast of Wind</h1>
<b>Source</b> <a>Ultimate Wilderness pg. 220</a><br/>
<b>School</b> evocation [air]; <b>Level</b> druid 2<br/>
<h3 class="framing">Description</h3>
A blast of wind <i>pushes</i> creatures away.<br/>Second paragraph.
<h1 class="title">Greater Blast of Wind</h1>
Variant text that must not leak.
</span></td></tr></table>
"""


def test_spell_description_solo_il_blocco_richiesto():
    d = spell_description(PAGE, "Blast of Wind")
    assert d.startswith("A blast of wind pushes creatures away.")
    assert "Second paragraph." in d
    assert "must not leak" not in d
    assert "evocation" not in d


def test_spell_entry_tag_nel_formato_del_catalogo():
    parsed = {
        "name": "Blast of Wind",
        "source": "Ultimate Wilderness",
        "references": ["AoN: Blast of Wind (Spells)"],
        "reference_urls": [
            "https://aonprd.com/SpellDisplay.aspx?ItemName=Blast%20of%20Wind"
        ],
        "mechanics": {
            "school": "evocation",
            "descriptors": ["air"],
            "spell_level": {"druid": 2, "shaman": 2},
        },
    }
    e = spell_entry(parsed, "A blast of wind pushes creatures away.")
    assert e["source_id"] == "spells:blast_of_wind"
    assert e["tags"] == [
        "school:evocation",
        "slot:2",
        "air",
        "class:druid",
        "class:shaman",
    ]
    assert e["prerequisites"] == []
    assert e["description"] == "A blast of wind pushes creatures away."
    assert e["mechanics"]["spell_level"] == {"druid": 2, "shaman": 2}


def test_missing_spells_numeri_romani_e_arabi_coincidono():
    catalogo = [{"name": "Summon Nature's Ally 3"}, {"name": "Fey Form I"}]
    indice_html = (
        "<a href='SpellDisplay.aspx?ItemName=Summon%20Nature%27s%20Ally%20III'>a</a>"
        "<a href='SpellDisplay.aspx?ItemName=Fey%20Form%20I'>b</a>"
        "<a href='SpellDisplay.aspx?ItemName=Blast%20of%20Wind'>c</a>"
    )
    assert missing_spells(indice_html, catalogo) == ["Blast of Wind"]


def test_main_write_aggiunge_in_coda_e_aggiorna_manifest(tmp_path, monkeypatch):
    import json

    import tools.import_spells_aon as mod

    spells = tmp_path / "spells.json"
    spells.write_text(json.dumps({"entries": [{"name": "Fireball"}]}), "utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {"spells": {"entries": 1}},
                "catalogs": [
                    {"kind": "spells", "entries": 1},
                    {"kind": "spells_local", "entries": 0},
                ],
            }
        ),
        "utf-8",
    )
    monkeypatch.setattr(mod, "SPELLS_PATH", spells)
    monkeypatch.setattr(mod, "LOCAL_PATH", tmp_path / "local" / "spells_local.json")
    monkeypatch.setattr(mod, "MANIFEST_PATH", manifest)
    indice = (
        "<a href='SpellDisplay.aspx?ItemName=Fireball'>a</a>"
        "<a href='SpellDisplay.aspx?ItemName=Blast%20of%20Wind'>b</a>"
    )
    monkeypatch.setattr(
        mod, "fetch", lambda url, delay=0: indice if "Spells.aspx" in url else PAGE
    )

    assert mod.main(["--write"]) == 0
    voci = json.loads(spells.read_text("utf-8"))["entries"]
    assert [e["name"] for e in voci] == ["Fireball", "Blast of Wind"]
    assert voci[1]["mechanics"]["school"] == "evocation"
    m = json.loads(manifest.read_text("utf-8"))
    assert m["files"]["spells"]["entries"] == 2


def test_main_pi_nella_descrizione_va_in_locale(tmp_path, monkeypatch):
    import json

    import tools.import_spells_aon as mod

    spells = tmp_path / "spells.json"
    spells.write_text(json.dumps({"entries": []}), "utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"files": {"spells": {"entries": 0}}, "catalogs": []}), "utf-8"
    )
    local = tmp_path / "local" / "spells_local.json"
    monkeypatch.setattr(mod, "SPELLS_PATH", spells)
    monkeypatch.setattr(mod, "LOCAL_PATH", local)
    monkeypatch.setattr(mod, "MANIFEST_PATH", manifest)
    indice = "<a href='SpellDisplay.aspx?ItemName=Blast%20of%20Wind'>b</a>"
    pagina = PAGE.replace("Second paragraph.", "It is sacred in Brevoy.")
    monkeypatch.setattr(
        mod, "fetch", lambda url, delay=0: indice if "Spells.aspx" in url else pagina
    )

    assert mod.main(["--write"]) == 0
    assert json.loads(spells.read_text("utf-8"))["entries"] == []
    nomi = [e["name"] for e in json.loads(local.read_text("utf-8"))["entries"]]
    assert nomi == ["Blast of Wind"]
