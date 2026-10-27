"""Test per tools/import_pathbuilder_magic_qualities.py — qualita' magiche PB.

Slice Fase A (2026-08-08, seguito D4): data_armor_magic.xml (68 qualita' per
armature/scudi) e data_weapon_effects.xml (97 qualita' per armi) diventano un
catalogo nome+categorie committato. MAI description (non esiste proprio nel
dato PI), MAI bonus inventati: le qualita' sono METADATA per un consumatore
futuro (legality equip D6 — il canale `proficiency` non le usa ancora).

Fixture XML inline (MAI rete): forma reale dei file (ricognizione
2026-08-08): <Row> con <Effect>/<Name>, <Categories> (codici numerici
separati da '&', stessa codifica di data_armor.xml/data_weapons.xml),
<Damage> opzionale solo su alcune weapon effects (es. "(2d6 v Lawful)").
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_magic_qualities as mq

ARMOR_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
	<Row>
		<Effect>Adhesive</Effect>
		<Categories>0&amp;1&amp;2</Categories>
	</Row>
	<Row>
		<Effect>Animated</Effect>
		<Categories>3&amp;4</Categories>
	</Row>
	<Row>
		<Effect>Balanced</Effect>
		<Categories>0&amp;1&amp;2&amp;5</Categories>
	</Row>
</Root>
"""

WEAPON_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
	<Row>
		<Name>Advancing</Name>
		<Categories>0&amp;1&amp;2&amp;6</Categories>
	</Row>
	<Row>
		<Name>Anarchic</Name>
		<Damage>(2d6 v Lawful)</Damage>
		<Categories>0&amp;1&amp;2&amp;3&amp;4&amp;5&amp;6</Categories>
	</Row>
	<Row>
		<Name>Bane</Name>
		<Categories>0&amp;1&amp;2&amp;3&amp;4&amp;5&amp;6</Categories>
	</Row>
</Root>
"""


def _raw_dir(tmp_path: Path) -> Path:
    (tmp_path / "data_armor_magic.xml").write_text(ARMOR_XML, encoding="utf-8")
    (tmp_path / "data_weapon_effects.xml").write_text(WEAPON_XML, encoding="utf-8")
    return tmp_path


def test_import_armor_magic_categorie_etichettate(tmp_path):
    entries = mq.import_armor_magic(_raw_dir(tmp_path))
    assert [e["name"] for e in entries] == ["Adhesive", "Animated", "Balanced"]
    adhesive = entries[0]
    assert adhesive["categories"] == [0, 1, 2]
    assert adhesive["categoryLabels"] == ["light", "medium", "heavy"]
    animated = entries[1]
    assert animated["categoryLabels"] == ["shield", "tower-shield"]
    # 5 = accessorio magico (Bracers of Armor), stessa mappa D4
    assert entries[2]["categoryLabels"] == [
        "light",
        "medium",
        "heavy",
        "magic-accessory",
    ]
    # MAI description/danno sulle qualita' armatura (non esistono nel dato)
    for e in entries:
        assert "description" not in {k.lower() for k in e}
        assert "damage" not in e


def test_import_weapon_effects_damage_grezzo_strutturato(tmp_path):
    entries = mq.import_weapon_effects(_raw_dir(tmp_path))
    assert [e["name"] for e in entries] == ["Advancing", "Anarchic", "Bane"]
    advancing = entries[0]
    assert advancing["categoryLabels"] == [
        "light",
        "one-handed",
        "two-handed",
        "natural",
    ]
    # il Damage e' presente SOLO dove nel dato (13 righe su 97 reali):
    # stringa grezza strutturata, MAI parsata a effetto meccanico
    assert "damage" not in advancing
    assert entries[1]["damage"] == "(2d6 v Lawful)"
    assert "damage" not in entries[2]


def test_build_payload_provenance_e_conteggi(tmp_path):
    payload = mq.build(_raw_dir(tmp_path))
    prov = payload["_provenance"]
    assert "Pathbuilder" in prov["source"]
    assert prov["license"]
    assert prov["desc_policy"]
    assert payload["counts"] == {"armorMagic": 3, "weaponEffects": 3}
    # le mappe codici sono ESPOSTE e coerenti con quelle D4
    assert payload["armorCategories"]["5"] == "magic-accessory"
    assert payload["weaponCategories"]["6"] == "natural"


def test_main_scrive_il_json(tmp_path):
    out = tmp_path / "out"
    rc = mq.main(["--raw-dir", str(_raw_dir(tmp_path)), "--out-dir", str(out)])
    assert rc == 0
    import json

    data = json.loads(
        (out / "pathbuilder-magic-qualities.json").read_text(encoding="utf-8")
    )
    assert data["armorMagic"] and data["weaponEffects"]


# ---------------------------------------------------------------------------
# Smoke sui dati REALI (skip se il dataset PI locale non c'e')
# ---------------------------------------------------------------------------

REAL_RAW = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "reference"
    / "pi_local_only"
    / "pathbuilder"
)


@pytest.mark.skipif(
    not (REAL_RAW / "data_armor_magic.xml").is_file(),
    reason="dataset PI Pathbuilder assente",
)
def test_dati_reali_conteggi_e_spot_check():
    payload = mq.build(REAL_RAW)
    assert payload["counts"]["armorMagic"] == 68
    assert payload["counts"]["weaponEffects"] == 97
    armor = {e["name"]: e for e in payload["armorMagic"]}
    weapons = {e["name"]: e for e in payload["weaponEffects"]}
    # spot-check RAW: qualita' note con le categorie attese
    assert armor["Animated"]["categoryLabels"] == ["shield", "tower-shield"]
    assert armor["Bashing"]["categoryLabels"] == ["shield"]
    assert weapons["Keen"]["categoryLabels"] == [
        "light",
        "one-handed",
        "two-handed",
        "natural",
    ]
    assert weapons["Anarchic"]["damage"] == "(2d6 v Lawful)"
    # il Damage e' raro: 13 righe su 97 (misurato 2026-08-08)
    with_damage = [e for e in payload["weaponEffects"] if "damage" in e]
    assert len(with_damage) == 13
    # nessun duplicato di nome dentro ogni catalogo
    assert len(armor) == len(payload["armorMagic"])
    assert len(weapons) == len(payload["weaponEffects"])
