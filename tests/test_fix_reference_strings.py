"""Test per tools/fix_reference_strings.py — bonifica references sanitize-order."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fix_reference_strings import fix_entry


def test_fix_entry_replaces_corrupted_reference():
    e = {"name": "X", "references": ["Archives of a deity of magic: X", "d20PFSRD: X"]}
    out, n = fix_entry(e)
    assert out["references"] == ["Pathfinder PRD: X", "d20PFSRD: X"]
    assert n == 1


def test_fix_entry_idempotent_and_untouched():
    e = {"name": "X", "references": ["Pathfinder PRD: X"]}
    out, n = fix_entry(e)
    assert out["references"] == ["Pathfinder PRD: X"]
    assert n == 0
