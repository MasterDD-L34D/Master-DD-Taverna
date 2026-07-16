"""Test per il pipeline di arricchimento reference."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tools.enrich_reference import (
    MANUAL_SEED,
    build_feat_lookup,
    build_spell_lookup,
    enrich_entry,
    normalize_name,
)


def test_normalize_name():
    assert normalize_name("Power Attack") == "powerattack"
    assert normalize_name("Furious Focus") == "furiousfocus"
    assert normalize_name("Cleave") == "cleave"
    assert normalize_name("Amulet of Natural Armor +1") == "amuletofnaturalarmor1"


def test_seed_has_iconic_entries():
    assert "Power Attack" in MANUAL_SEED["feats"]
    assert "Fireball" in MANUAL_SEED["spells"]
    assert "Amulet of Natural Armor +1" in MANUAL_SEED["items"]


def test_enrich_entry_with_seed():
    entry = {"name": "Power Attack", "prerequisites": ["Strength 13"]}
    modified = enrich_entry(
        entry,
        "feats",
        feat_lookup={},
        spell_lookup={},
        manual_seed=MANUAL_SEED,
        force=False,
        allow_scrape=False,
    )
    assert modified is True
    assert "description" in entry
    assert "Benefit" in entry["description"]
    assert "Italiano" in entry["description"]


def test_enrich_entry_no_overwrite_without_force():
    entry = {"name": "Power Attack", "description": "existing", "prerequisites": []}
    modified = enrich_entry(
        entry,
        "feats",
        feat_lookup={},
        spell_lookup={},
        manual_seed=MANUAL_SEED,
        force=False,
        allow_scrape=False,
    )
    assert modified is False
    assert entry["description"] == "existing"


def test_feat_lookup_loads():
    lookup = build_feat_lookup(extended=False, max_workers=4)
    assert len(lookup) > 1000
    assert normalize_name("Power Attack") in lookup
    assert "description" in lookup[normalize_name("Cleave")]


def test_spell_lookup_loads():
    lookup = build_spell_lookup()
    assert len(lookup) > 1000
    assert normalize_name("Fireball") in lookup
    assert "description" in lookup[normalize_name("Magic Missile")]
