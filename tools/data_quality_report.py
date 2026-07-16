from __future__ import annotations

"""Generate data quality metrics for Pathfinder Master DD datasets."""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

DEFAULT_BUILD_INDEX = Path("src/data/build_index.json")
DEFAULT_MODULE_INDEX = Path("src/data/module_index.json")
DEFAULT_MANIFEST = Path("data/reference/manifest.json")
DEFAULT_OUTPUT = Path("reports/data_quality_report.json")
EXPECTED_LEVELS = {1, 5, 10}
ALLOWED_BUILD_STATUS = {"ok", "invalid", "error"}
ALLOWED_MODULE_STATUS = {"ok"}


@dataclass
class TableQuality:
    name: str
    rows: int
    null_percentages: Mapping[str, float]
    duplicate_counts: Mapping[str, int]
    out_of_domain: Mapping[str, list[Any]]
    referential_issues: Mapping[str, list[str]]
    coverage_gaps: list[Mapping[str, Any]]

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "rows": self.rows,
            "null_percentages": self.null_percentages,
            "duplicate_counts": self.duplicate_counts,
            "out_of_domain": self.out_of_domain,
            "referential_issues": self.referential_issues,
            "coverage_gaps": self.coverage_gaps,
        }


def is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) == 0
    return False


def percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def null_percentages(
    records: Iterable[Mapping[str, Any]], fields: Iterable[str]
) -> Mapping[str, float]:
    records_list = list(records)
    total = len(records_list)
    result: dict[str, float] = {}
    for field in fields:
        nulls = sum(1 for record in records_list if is_nullish(record.get(field)))
        result[field] = percentage(nulls, total)
    return result


def duplicate_counts(
    records: Iterable[Mapping[str, Any]], key_fields: Iterable[str]
) -> Mapping[str, int]:
    result: dict[str, int] = {}
    records_list = list(records)
    for field in key_fields:
        counter = Counter(record.get(field) for record in records_list)
        result[field] = sum(count for count in counter.values() if count > 1)
    return result


def duplicate_on_tuple(
    records: Iterable[Mapping[str, Any]], key_fields: Iterable[str]
) -> int:
    counter: Counter[tuple[Any, ...]] = Counter()
    for record in records:
        counter[tuple(record.get(field) for field in key_fields)] += 1
    return sum(count for count in counter.values() if count > 1)


def validate_urls(urls: Iterable[str]) -> list[str]:
    invalid: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            invalid.append(url)
    return invalid


def analyze_build_index(path: Path, manifest_version: str | None) -> TableQuality:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: list[Mapping[str, Any]] = data.get("entries", [])

    nulls = null_percentages(
        entries,
        (
            "file",
            "status",
            "output_prefix",
            "class",
            "race",
            "archetype",
            "mode",
            "mode_normalized",
            "spec_id",
            "level",
        ),
    )

    duplicates = duplicate_counts(entries, ("file", "spec_id", "output_prefix"))
    duplicates["spec_id_level"] = duplicate_on_tuple(entries, ("spec_id", "level"))

    out_of_domain: dict[str, list[Any]] = {
        "status": [
            record.get("status")
            for record in entries
            if record.get("status") not in ALLOWED_BUILD_STATUS
        ],
        "level": [
            record.get("level")
            for record in entries
            if record.get("level") is not None
            and record.get("level") not in EXPECTED_LEVELS
        ],
    }

    referential: dict[str, list[str]] = defaultdict(list)
    for record in entries:
        file_ref = record.get("file")
        if is_nullish(file_ref):
            referential["missing_files"].append(
                f"{record.get('module') or record.get('spec_id') or 'unknown'}: file mancante"
            )
            continue
        file_path = Path(str(file_ref))
        if not file_path.exists():
            referential["missing_files"].append(str(file_path))
        if manifest_version is not None:
            catalog_version = record.get("catalog_version")
            if manifest_version not in (catalog_version or []):
                referential["catalog_version_mismatch"].append(str(file_path))

    coverage_gaps: list[Mapping[str, Any]] = []
    grouped: dict[str, set[int]] = defaultdict(set)
    expected_levels: dict[str, set[int]] = defaultdict(lambda: set(EXPECTED_LEVELS))
    mandatory_missing: list[Mapping[str, Any]] = []

    for record in entries:
        prefix = str(record.get("output_prefix") or record.get("spec_id") or "")
        level = record.get("level")
        checkpoints = record.get("level_checkpoints")
        if isinstance(checkpoints, list) and checkpoints:
            expected_levels[prefix] = {
                lvl for lvl in checkpoints if isinstance(lvl, int)
            } or set(EXPECTED_LEVELS)
        if isinstance(level, int):
            grouped[prefix].add(level)
        else:
            coverage_gaps.append(
                {
                    "file": record.get("file"),
                    "issue": "level_missing",
                    "details": "Campo level assente o nullo",
                }
            )

        missing_fields = [
            field
            for field in ("file", "output_prefix", "class", "race", "mode", "spec_id")
            if is_nullish(record.get(field))
        ]
        if missing_fields:
            mandatory_missing.append(
                {
                    "file": record.get("file"),
                    "missing_fields": missing_fields,
                }
            )

    for prefix, expected in expected_levels.items():
        missing_levels = sorted(expected - grouped.get(prefix, set()))
        if missing_levels:
            coverage_gaps.append(
                {
                    "output_prefix": prefix,
                    "issue": "missing_levels",
                    "expected_levels": sorted(expected),
                    "missing_levels": missing_levels,
                }
            )

    if mandatory_missing:
        coverage_gaps.append(
            {
                "issue": "mandatory_fields_missing",
                "rows": mandatory_missing,
            }
        )

    return TableQuality(
        name="build_index",
        rows=len(entries),
        null_percentages=nulls,
        duplicate_counts=duplicates,
        out_of_domain=out_of_domain,
        referential_issues=referential,
        coverage_gaps=coverage_gaps,
    )


def analyze_module_index(path: Path, manifest_version: str | None) -> TableQuality:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: list[Mapping[str, Any]] = data.get("entries", [])

    nulls = null_percentages(entries, ("module", "file", "status"))
    duplicates = duplicate_counts(entries, ("module", "file"))

    out_of_domain: dict[str, list[Any]] = {
        "status": [
            record.get("status")
            for record in entries
            if record.get("status") not in ALLOWED_MODULE_STATUS
        ]
    }

    referential: dict[str, list[str]] = defaultdict(list)
    for record in entries:
        file_ref = record.get("file")
        if is_nullish(file_ref):
            referential["missing_files"].append(
                f"{record.get('module') or 'unknown'}: file mancante"
            )
            continue
        file_path = Path(str(file_ref))
        if not file_path.exists():
            referential["missing_files"].append(str(file_path))
        if manifest_version is not None:
            catalog_version = record.get("meta", {}).get(
                "catalog_version"
            ) or record.get("catalog_version")
            if catalog_version and manifest_version not in catalog_version:
                referential["catalog_version_mismatch"].append(str(file_path))

    coverage_gaps: list[Mapping[str, Any]] = []
    missing_fields_rows: list[Mapping[str, Any]] = []
    for record in entries:
        missing = [
            field
            for field in ("module", "file", "status")
            if is_nullish(record.get(field))
        ]
        if missing:
            missing_fields_rows.append(
                {"file": record.get("file"), "missing_fields": missing}
            )
    if missing_fields_rows:
        coverage_gaps.append(
            {"issue": "mandatory_fields_missing", "rows": missing_fields_rows}
        )

    return TableQuality(
        name="module_index",
        rows=len(entries),
        null_percentages=nulls,
        duplicate_counts=duplicates,
        out_of_domain=out_of_domain,
        referential_issues=referential,
        coverage_gaps=coverage_gaps,
    )


def analyze_reference_catalog(
    manifest: Mapping[str, Any], manifest_path: Path
) -> TableQuality:
    files = manifest.get("files", {}) if isinstance(manifest, Mapping) else {}
    datasets: dict[str, list[Mapping[str, Any]]] = {}
    referential: dict[str, list[str]] = defaultdict(list)

    for key, info in files.items():
        raw_path = info.get("path")
        if not isinstance(raw_path, str):
            referential["missing_files"].append(f"{key}: path non valorizzato")
            continue

        path = Path(raw_path)
        if not path.exists():
            fallback = manifest_path.parent / raw_path
            path = fallback

        if not path.exists():
            referential["missing_files"].append(str(path))
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        datasets[key] = data
        expected_entries = info.get("entries")
        if isinstance(expected_entries, int) and expected_entries != len(data):
            referential["entry_count_mismatch"].append(
                f"{key}: expected {expected_entries}, found {len(data)}"
            )

    total_rows = sum(len(items) for items in datasets.values())
    combined_entries = [entry for items in datasets.values() for entry in items]

    nulls = null_percentages(
        combined_entries,
        ("name", "source", "prerequisites", "tags", "references"),
    )

    duplicates = {"name": duplicate_counts(combined_entries, ("name",)).get("name", 0)}

    out_of_domain: dict[str, list[Any]] = defaultdict(list)
    for entry in combined_entries:
        urls = entry.get("reference_urls") or []
        if isinstance(urls, list):
            invalid_urls = validate_urls([u for u in urls if isinstance(u, str)])
            if invalid_urls:
                out_of_domain["invalid_reference_urls"].extend(invalid_urls)
        tags = entry.get("tags")
        if isinstance(tags, list):
            non_strings = [tag for tag in tags if not isinstance(tag, str)]
            if non_strings:
                out_of_domain["invalid_tags"].extend(non_strings)

    coverage_gaps: list[Mapping[str, Any]] = []
    missing_required: list[Mapping[str, Any]] = []
    for entry in combined_entries:
        missing = [
            field
            for field in ("name", "source", "references")
            if is_nullish(entry.get(field))
        ]
        if missing:
            missing_required.append(
                {"name": entry.get("name"), "missing_fields": missing}
            )
    if missing_required:
        coverage_gaps.append(
            {"issue": "mandatory_fields_missing", "rows": missing_required}
        )

    return TableQuality(
        name="reference_catalog",
        rows=total_rows,
        null_percentages=nulls,
        duplicate_counts=duplicates,
        out_of_domain=out_of_domain,
        referential_issues=referential,
        coverage_gaps=coverage_gaps,
    )


def build_report(
    build_index: Path = DEFAULT_BUILD_INDEX,
    module_index: Path = DEFAULT_MODULE_INDEX,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> Mapping[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = (
        manifest.get("version") if isinstance(manifest, Mapping) else None
    )

    build_table = analyze_build_index(build_index, manifest_version)
    module_table = analyze_module_index(module_index, manifest_version)
    reference_table = analyze_reference_catalog(manifest, manifest_path)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            build_table.name: build_table.to_dict(),
            module_table.name: module_table.to_dict(),
            reference_table.name: reference_table.to_dict(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate data quality report for key datasets"
    )
    parser.add_argument(
        "--build-index",
        type=Path,
        default=DEFAULT_BUILD_INDEX,
        help="Path to build_index.json",
    )
    parser.add_argument(
        "--module-index",
        type=Path,
        default=DEFAULT_MODULE_INDEX,
        help="Path to module_index.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to reference manifest",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the quality report JSON",
    )
    args = parser.parse_args()

    report = build_report(args.build_index, args.module_index, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
