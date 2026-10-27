"""Test per tools/validate_monsters.py — validazione CR-band report-only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.validate_monsters import (
    avg_damage,
    max_attack_bonus,
    max_group_damage,
    validate,
)


def _entry(name, cr, hp, ac, fort, ref_, will, attacks=None):
    return {
        "name": name,
        "mechanics": {
            "cr": cr,
            "hp": hp,
            "ac": ac,
            "saves": {"fort": fort, "ref": ref_, "will": will},
            "attacks": attacks or {},
        },
    }


def test_avg_damage_parses_dice_expressions():
    assert avg_damage("2d6+5") == 12.0
    assert avg_damage("1d8-1") == 3.5
    assert avg_damage("3d6") == 10.5
    assert avg_damage("nessun dado") == 0.0


def test_max_attack_bonus_and_group_damage():
    attacks = {
        "melee": [
            [
                {
                    "text": "bite +13 (2d6+5)",
                    "bonus": [13],
                    "entries": [[{"damage": "2d6+5"}]],
                },
                {
                    "text": "2 stings +13 (1d6+5)",
                    "count": 2,
                    "bonus": [13],
                    "entries": [[{"damage": "1d6+5"}]],
                },
            ]
        ]
    }
    assert max_attack_bonus(attacks) == 13
    # 12.0 + 2 * 8.5 = 29.0
    assert max_group_damage(attacks) == 29.0


def test_validate_in_band_monster_has_no_findings():
    # CR 5 benchmark: hp 55, ac 18, atk 10/7, dmg 20/15, saves 8/4
    e = _entry(
        "In Band",
        5,
        55,
        18,
        8,
        6,
        5,
        attacks={
            "melee": [
                [
                    {
                        "text": "slam +10 (2d6+7)",
                        "bonus": [10],
                        "entries": [[{"damage": "2d6+7"}]],
                    }
                ]
            ]
        },
    )
    findings = validate([e])
    assert findings == []


def test_validate_flags_out_of_band_hp():
    e = _entry(
        "Glass Cannon",
        5,
        10,
        18,
        8,
        6,
        5,
        attacks={
            "melee": [
                [
                    {
                        "text": "slam +10 (2d6+7)",
                        "bonus": [10],
                        "entries": [[{"damage": "2d6+7"}]],
                    }
                ]
            ]
        },
    )
    findings = validate([e])
    assert len(findings) == 1
    assert findings[0]["field"] == "hp"
    assert findings[0]["name"] == "Glass Cannon"


def test_validate_cr_out_of_benchmark_range():
    e = _entry("Mythic Thing", 25, 500, 40, 20, 18, 18)
    findings = validate([e])
    assert findings == [
        {
            "name": "Mythic Thing",
            "cr": 25,
            "field": "cr",
            "value": 25,
            "note": "fuori range benchmark (0.5-20)",
        }
    ]


def test_validate_flags_35_legacy_via_source_map():
    e = _entry(
        "Old Critter",
        5,
        55,
        18,
        8,
        6,
        5,
        attacks={
            "melee": [
                [
                    {
                        "text": "slam +10 (2d6+7)",
                        "bonus": [10],
                        "entries": [[{"damage": "2d6+7"}]],
                    }
                ]
            ]
        },
    )
    findings = validate([e], legacy_35={"Old Critter"})
    assert findings == [
        {
            "name": "Old Critter",
            "cr": 5,
            "field": "legacy",
            "value": True,
            "note": "statblock 3.5 legacy (is_3.5)",
        }
    ]
