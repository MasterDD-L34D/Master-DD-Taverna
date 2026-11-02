"""Test per tools/import_magic_items_aon.py -- oggetti magici da AoN (2026-11-02).

Il censimento AoN vs catalogo del 2026-11-01 ha trovato items.json all'1%
(257 voci contro ~3800 famiglie). Una voce per FAMIGLIA: la pagina di
dettaglio AoN e' una per famiglia, con tutte le varianti (+1..+5) dentro.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_magic_items_aon import (
    index_families,
    item_entry,
    missing_families,
    parse_item_page,
)

# Forma reale di MagicWondrous.aspx?FinalSlot=Shoulders: link
# MagicWondrousDisplay.aspx?FinalName=<variante incollata>, testo del link
# "Famiglia (variante)".
INDEX = """
<table><tr><td>Name</td><td>Cost</td></tr>
<tr><td><a href="MagicWondrousDisplay.aspx?FinalName=Catching Cape">Catching Cape</a></td></tr>
<tr><td><a href="MagicWondrousDisplay.aspx?FinalName=Cloak of Resistance1">Cloak of Resistance (+1)</a></td></tr>
<tr><td><a href="MagicWondrousDisplay.aspx?FinalName=Cloak of Resistance2">Cloak of Resistance (+2)</a></td></tr>
<tr><td><a href="Rules.aspx?Name=x">regole</a></td></tr>
</table>
"""


def test_index_families_raggruppa_le_varianti():
    fams = index_families(INDEX, "MagicWondrousDisplay.aspx")
    assert fams == [
        {
            "family": "Catching Cape",
            "final_name": "Catching Cape",
            "param": "FinalName",
            "variants": [],
        },
        {
            "family": "Cloak of Resistance",
            "final_name": "Cloak of Resistance1",
            "param": "FinalName",
            "variants": ["+1", "+2"],
        },
    ]


def test_index_families_accetta_anche_itemname():
    # Staves, armi, armature, qualita', artefatti... linkano con ItemName=
    # (verificato sugli indici reali il 2026-11-02), non con FinalName=.
    html = (
        "<a href='MagicStavesDisplay.aspx?ItemName=Staff%20of%20Blessed%20Relief'>"
        "Staff of Blessed Relief</a>"
    )
    assert index_families(html, "MagicStavesDisplay.aspx") == [
        {
            "family": "Staff of Blessed Relief",
            "final_name": "Staff of Blessed Relief",
            "param": "ItemName",
            "variants": [],
        }
    ]


# Frammento reale (2026-11-02) di MagicWondrousDisplay.aspx?FinalName=Cloak of
# Resistance1, accorciato nei prezzi.
CLOAK = """
<table id="MainContent_DataListTypes"><tr><td><span>
<h1 class="title">Cloak of Resistance</h1><b>Source</b> <a><i>Ultimate Equipment pg. 264</i></a>,
<a><i>PRPG Core Rulebook pg. 507</i></a><br><b>Aura</b> faint abjuration; <b>CL</b> 5th<br>
<b>Slot</b> shoulders; <b>Price</b> 1,000 gp (<img title="PFS Legal"> +1), 4,000 gp (+2);
<b>Weight</b> 1 lb.<h3 class="framing">Description</h3>Flecks of silver are sown amid the
fabric. This garment offers a +1 to +5 resistance bonus on all saving throws.
<h3 class="framing">Construction</h3><b>Requirements</b> Craft Wondrous Item, <i>resistance</i>,
creator's caster level must be at least three times the cloak's bonus; <b>Cost</b> 500 gp (+1),
2,000 gp (+2)</span></td></tr></table>
"""


def test_parse_item_page_campi_sezioni_e_fonte_core():
    p = parse_item_page(CLOAK)
    assert p["name"] == "Cloak of Resistance"
    assert p["source"] == "PRPG Core Rulebook"
    assert p["aura"] == "faint abjuration"
    assert p["cl"] == "5th"
    assert p["slot"] == "shoulders"
    assert p["price"] == "1,000 gp (+1), 4,000 gp (+2)"
    assert p["weight"] == "1 lb."
    assert p["description"].startswith("Flecks of silver are sown amid the fabric.")
    assert p["requirements"] == [
        "Craft Wondrous Item",
        "resistance",
        "creator's caster level must be at least three times the cloak's bonus",
    ]
    assert p["cost"] == "500 gp (+1), 2,000 gp (+2)"


def test_parse_item_page_price_nella_costruzione_e_il_costo():
    # Forma reale delle armi specifiche (Darkness Arrow, 2026-11-02): la
    # sezione Construction chiama il costo "Price", non "Cost".
    html = (
        '<table id="MainContent_DataListTypes"><tr><td><span>'
        '<h1 class="title">Darkness Arrow</h1><b>Source</b> <i>Villain Codex pg. 9</i><br>'
        "<b>Aura</b> faint transmutation; <b>CL</b> 3rd<br><b>Slot</b> none; "
        "<b>Price</b> 80 gp ; <b>Weight</b> —"
        '<h3 class="framing">Description</h3>This arrow is black.'
        '<h3 class="framing">Construction</h3><b>Requirements</b> Craft Magic Arms '
        "and Armor, <i>darkness</i>; <b>Price</b> 40 gp</span></td></tr></table>"
    )
    p = parse_item_page(html)
    assert p["price"] == "80 gp"
    assert p["cost"] == "40 gp"
    assert p["requirements"] == ["Craft Magic Arms and Armor", "darkness"]


def test_item_entry_forma_del_catalogo():
    url = "https://aonprd.com/MagicWondrousDisplay.aspx?FinalName=Cloak%20of%20Resistance1"
    e = item_entry(parse_item_page(CLOAK), "wondrous", url, ["+1", "+2"])
    assert e["name"] == "Cloak of Resistance"
    assert e["source_id"] == "items:cloak_of_resistance"
    assert e["tags"] == ["wondrous", "slot:shoulders"]
    assert e["prerequisites"][0] == "Craft Wondrous Item"
    assert e["reference_urls"] == [url]
    assert e["description"].startswith("Flecks of silver")
    assert e["mechanics"] == {
        "category": "wondrous",
        "aura": "faint abjuration",
        "cl": "5th",
        "slot": "shoulders",
        "price": "1,000 gp (+1), 4,000 gp (+2)",
        "weight": "1 lb.",
        "cost": "500 gp (+1), 2,000 gp (+2)",
        "variants": ["+1", "+2"],
    }


def test_missing_families_toglie_bonus_e_variante_dai_nomi_esistenti():
    catalogo = [
        {"name": "Cloak of Resistance +1"},
        {"name": "Bag of Holding (Type I)"},
        {"name": "Ring of Protection +2"},
    ]
    fams = [
        {"family": "Cloak of Resistance"},
        {"family": "Bag of Holding"},
        {"family": "Ring of Protection"},
        {"family": "Catching Cape"},
    ]
    assert [f["family"] for f in missing_families(fams, catalogo)] == ["Catching Cape"]


def test_main_write_una_voce_per_famiglia_e_manifest(tmp_path, monkeypatch):
    import json

    import tools.import_magic_items_aon as mod

    items = tmp_path / "items.json"
    items.write_text(json.dumps({"entries": [{"name": "Catching Cape"}]}), "utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {"items": {"entries": 1}},
                "catalogs": [{"kind": "items", "entries": 1}],
            }
        ),
        "utf-8",
    )
    monkeypatch.setattr(mod, "ITEMS_PATH", items)
    monkeypatch.setattr(mod, "LOCAL_PATH", tmp_path / "local" / "items_local.json")
    monkeypatch.setattr(mod, "MANIFEST_PATH", manifest)
    # Due indici che elencano la stessa famiglia: una voce sola.
    monkeypatch.setattr(
        mod,
        "INDEXES",
        [
            ("https://aonprd.com/IdxA", "MagicWondrousDisplay.aspx", "wondrous"),
            ("https://aonprd.com/IdxB", "MagicWondrousDisplay.aspx", "wondrous"),
        ],
    )
    monkeypatch.setattr(
        mod, "fetch", lambda url, delay=0: INDEX if "Idx" in url else CLOAK
    )

    assert mod.main(["--write"]) == 0
    voci = json.loads(items.read_text("utf-8"))["entries"]
    assert [e["name"] for e in voci] == ["Catching Cape", "Cloak of Resistance"]
    assert voci[1]["mechanics"]["variants"] == ["+1", "+2"]
    assert json.loads(manifest.read_text("utf-8"))["files"]["items"]["entries"] == 2
