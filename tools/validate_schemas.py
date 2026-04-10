#!/usr/bin/env python3
"""Validate repository schemas and the reference catalog version contract.

The script validates all `*.schema.json` under `schemas/` and enforces a
versioning contract between:

- `data/reference/manifest.json`
- the `data/reference/*.json` datasets listed in the manifest
- `reference_catalog_version` inside build payload JSON files

It exits with non-zero status when any mismatch is found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


DEFAULT_BUILD_DIR_CANDIDATES = (
    Path("builds"),
    Path("data/builds"),
    Path("reports/builds"),
)
REQUIRED_REFERENCE_DATASETS = ("spells", "feats", "items")


def iter_schema_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.glob("*.schema.json")):
        if path.is_file():
            yield path


def validate_schema(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
    except SchemaError as exc:
        return f"{path}: schema non valida — {exc.message}"
    except Exception as exc:  # pragma: no cover - defensive logging
        return f"{path}: errore di lettura/parse — {exc}"
    return None


def _manifest_file_paths(
    manifest_payload: Mapping[str, object], manifest_path: Path
) -> tuple[dict[str, Path], list[str]]:
    errors: list[str] = []
    files_node = manifest_payload.get("files")
    if not isinstance(files_node, Mapping):
        return {}, [f"{manifest_path}: campo 'files' mancante o non oggetto"]

    resolved: dict[str, Path] = {}
    for dataset_name, descriptor in files_node.items():
        if not isinstance(descriptor, Mapping):
            errors.append(
                f"{manifest_path}: files.{dataset_name} non è un oggetto valido"
            )
            continue
        raw_path = descriptor.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(
                f"{manifest_path}: files.{dataset_name}.path mancante o non stringa"
            )
            continue

        candidate = Path(raw_path)
        if candidate.is_absolute():
            resolved_path = candidate
        else:
            manifest_anchor = (
                manifest_path.parents[2]
                if len(manifest_path.parents) >= 3
                else manifest_path.parent
            )
            anchor_relative = (manifest_anchor / candidate).resolve()
            repo_relative = (Path.cwd() / candidate).resolve()
            manifest_relative = (manifest_path.parent / candidate).resolve()
            if anchor_relative.exists():
                resolved_path = anchor_relative
            elif repo_relative.exists():
                resolved_path = repo_relative
            else:
                resolved_path = manifest_relative
        resolved[dataset_name] = resolved_path

    return resolved, errors


def validate_reference_contract(
    manifest_path: Path, build_dirs: Iterable[Path]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not manifest_path.is_file():
        return [f"Manifest non trovato: {manifest_path}"], warnings

    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{manifest_path}: errore lettura/parse manifest — {exc}"], warnings

    if not isinstance(manifest_payload, Mapping):
        return [f"{manifest_path}: il manifest deve essere un oggetto JSON"], warnings

    manifest_version = manifest_payload.get("version")
    if not isinstance(manifest_version, str) or not manifest_version.strip():
        errors.append(f"{manifest_path}: campo 'version' mancante o non stringa")

    manifest_files, manifest_file_errors = _manifest_file_paths(
        manifest_payload, manifest_path
    )
    errors.extend(manifest_file_errors)

    missing_required_datasets = [
        dataset for dataset in REQUIRED_REFERENCE_DATASETS if dataset not in manifest_files
    ]
    if missing_required_datasets:
        errors.append(
            f"{manifest_path}: dataset obbligatori mancanti nel manifest ({', '.join(missing_required_datasets)})"
        )

    if manifest_files:
        for dataset_name, dataset_path in manifest_files.items():
            if not dataset_path.is_file():
                errors.append(
                    f"{manifest_path}: files.{dataset_name}.path punta a file assente ({dataset_path})"
                )
                continue
            try:
                dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{dataset_path}: errore lettura/parse dataset — {exc}")
                continue
            if not isinstance(dataset_payload, list):
                errors.append(f"{dataset_path}: dataset deve essere una lista JSON")
                continue
            descriptor = (manifest_payload.get("files") or {}).get(dataset_name)
            expected_entries = (
                descriptor.get("entries") if isinstance(descriptor, Mapping) else None
            )
            if isinstance(expected_entries, int):
                actual_entries = len(dataset_payload)
                if actual_entries != expected_entries:
                    errors.append(
                        f"{dataset_path}: entries={actual_entries} non coerente con manifest ({expected_entries})"
                    )
            else:
                errors.append(
                    f"{manifest_path}: files.{dataset_name}.entries mancante o non intero"
                )

        reference_dir = manifest_path.parent
        dataset_files = {
            path.resolve()
            for path in reference_dir.glob("*.json")
            if path.name != "manifest.json"
        }
        manifest_declared_files = set(manifest_files.values())
        for missing in sorted(dataset_files - manifest_declared_files):
            errors.append(
                f"{manifest_path}: dataset presente ma non dichiarato nel manifest ({missing})"
            )

    scanned_payloads = 0
    for build_dir in build_dirs:
        if not build_dir.exists():
            continue
        for payload_path in sorted(build_dir.rglob("*.json")):
            if not payload_path.is_file():
                continue
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{payload_path}: JSON non leggibile — {exc}")
                continue
            if not isinstance(payload, Mapping):
                continue

            maybe_build = (
                "reference_catalog_version" in payload
                or "build_id" in payload
                or "build_state" in payload
                or "composite" in payload
            )
            if not maybe_build:
                continue

            scanned_payloads += 1
            payload_version = payload.get("reference_catalog_version")
            if payload_version != manifest_version:
                errors.append(
                    f"{payload_path}: reference_catalog_version={payload_version!r} diverso dal manifest={manifest_version!r}"
                )

            composite = payload.get("composite")
            if isinstance(composite, Mapping):
                composite_build = composite.get("build")
                if isinstance(composite_build, Mapping):
                    composite_version = composite_build.get("reference_catalog_version")
                    if composite_version != manifest_version:
                        errors.append(
                            f"{payload_path}: composite.build.reference_catalog_version={composite_version!r} diverso dal manifest={manifest_version!r}"
                        )

    if scanned_payloads == 0:
        warnings.append(
            "Nessun payload build trovato nelle directory candidate; salto controllo reference_catalog_version sui payload."
        )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate JSON schemas and reference catalog version contract"
    )
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=Path("schemas"),
        help="Directory contenente i file *.schema.json (default: schemas)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/reference/manifest.json"),
        help="Path del manifest reference (default: data/reference/manifest.json)",
    )
    parser.add_argument(
        "--build-dir",
        dest="build_dirs",
        action="append",
        type=Path,
        default=None,
        help=(
            "Directory da scandire per payload build JSON; ripetibile. "
            "Default: builds, data/builds, reports/builds"
        ),
    )

    args = parser.parse_args()
    build_dirs = args.build_dirs or list(DEFAULT_BUILD_DIR_CANDIDATES)

    errors = [
        issue
        for schema in iter_schema_files(args.schemas_dir)
        if (issue := validate_schema(schema))
    ]

    reference_errors, reference_warnings = validate_reference_contract(
        args.manifest, build_dirs
    )
    errors.extend(reference_errors)

    for warning in reference_warnings:
        print(f"[WARN] {warning}", file=sys.stderr)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        f"Schemi in {args.schemas_dir} validi e contratto versioni reference coerente."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
