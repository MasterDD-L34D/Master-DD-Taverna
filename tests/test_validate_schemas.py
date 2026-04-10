import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tools.validate_schemas import validate_reference_contract


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_reference_contract_accepts_manifest_and_payload_alignment(tmp_path: Path) -> None:
    _write_json(tmp_path / "data/reference/spells.json", [{"name": "A"}])
    _write_json(tmp_path / "data/reference/feats.json", [{"name": "B"}, {"name": "C"}])
    _write_json(tmp_path / "data/reference/items.json", [{"name": "D"}])
    _write_json(
        tmp_path / "data/reference/manifest.json",
        {
            "version": "2026.04.10",
            "files": {
                "spells": {"path": "data/reference/spells.json", "entries": 1},
                "feats": {"path": "data/reference/feats.json", "entries": 2},
                "items": {"path": "data/reference/items.json", "entries": 1},
            },
        },
    )
    _write_json(
        tmp_path / "data/builds/sample.json",
        {
            "build_id": "ok-1",
            "build_state": {},
            "reference_catalog_version": "2026.04.10",
            "composite": {"build": {"reference_catalog_version": "2026.04.10"}},
        },
    )

    errors, warnings = validate_reference_contract(
        tmp_path / "data/reference/manifest.json", [tmp_path / "data/builds"]
    )

    assert errors == []
    assert warnings == []


def test_reference_contract_requires_spells_feats_items_in_manifest(tmp_path: Path) -> None:
    _write_json(tmp_path / "data/reference/spells.json", [{"name": "A"}])
    _write_json(
        tmp_path / "data/reference/manifest.json",
        {
            "version": "2026.04.10",
            "files": {
                "spells": {"path": "data/reference/spells.json", "entries": 1},
            },
        },
    )

    errors, _ = validate_reference_contract(
        tmp_path / "data/reference/manifest.json", [tmp_path / "data/builds"]
    )

    assert any("dataset obbligatori mancanti" in err for err in errors)


def test_reference_contract_fails_on_reference_catalog_version_mismatch(tmp_path: Path) -> None:
    _write_json(tmp_path / "data/reference/spells.json", [{"name": "A"}])
    _write_json(tmp_path / "data/reference/feats.json", [{"name": "B"}])
    _write_json(tmp_path / "data/reference/items.json", [{"name": "C"}])
    _write_json(
        tmp_path / "data/reference/manifest.json",
        {
            "version": "2026.04.10",
            "files": {
                "spells": {"path": "data/reference/spells.json", "entries": 1},
                "feats": {"path": "data/reference/feats.json", "entries": 1},
                "items": {"path": "data/reference/items.json", "entries": 1},
            },
        },
    )
    _write_json(
        tmp_path / "data/builds/sample.json",
        {
            "build_id": "bad-1",
            "build_state": {},
            "reference_catalog_version": "2026.03.01",
            "composite": {"build": {"reference_catalog_version": "2026.03.01"}},
        },
    )

    errors, _ = validate_reference_contract(
        tmp_path / "data/reference/manifest.json", [tmp_path / "data/builds"]
    )

    assert any("reference_catalog_version" in err for err in errors)
