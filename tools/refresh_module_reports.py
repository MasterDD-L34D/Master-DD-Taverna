#!/usr/bin/env python3
"""Normalize module QA reports with standard sections.

The script reads the module sequence from `planning/module_review_guide.md`
(via the helper in `tools/generate_module_plan.py`) and ensures that every
report in `reports/module_tests/` contains the standard headings in order:
Ambiente, Esiti API, Metadati, Comandi/Flow, QA, Osservazioni, Errori,
Miglioramenti, Fix necessari.

Run with `--check` to validate presence and minimum content (at least one
bullet per section) or with `--write` to create/update files and inject
placeholder bullets where sections are missing or empty. If the source
module file is not found in `src/modules/`, a warning is emitted but the
report is still processed.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.generate_module_plan import (
    ALIASES,
    REPORT_DIR,
    find_report,
    load_sequence_from_guide,
    map_reports,
    normalise_name,
)

MODULE_DIR = REPO_ROOT / "src" / "modules"
PLACEHOLDER = "- TODO"


@dataclass
class SectionSpec:
    title: str
    patterns: Sequence[re.Pattern[str]]

    def matches(self, heading: str) -> bool:
        return any(pattern.search(heading) for pattern in self.patterns)


@dataclass
class SectionBlock:
    heading: str
    start: int
    end: int


SECTION_SPECS: List[SectionSpec] = [
    SectionSpec("Ambiente", [re.compile(r"^ambiente", re.IGNORECASE)]),
    SectionSpec(
        "Esiti API",
        [re.compile(r"esiti\s+api", re.IGNORECASE), re.compile(r"api", re.IGNORECASE)],
    ),
    SectionSpec(
        "Metadati",
        [re.compile(r"metadati", re.IGNORECASE), re.compile(r"scopo", re.IGNORECASE)],
    ),
    SectionSpec(
        "Comandi/Flow",
        [
            re.compile(r"comandi", re.IGNORECASE),
            re.compile(r"flow", re.IGNORECASE),
            re.compile(r"cta", re.IGNORECASE),
        ],
    ),
    SectionSpec("QA", [re.compile(r"^qa", re.IGNORECASE)]),
    SectionSpec("Osservazioni", [re.compile(r"osservaz", re.IGNORECASE)]),
    SectionSpec("Errori", [re.compile(r"errori", re.IGNORECASE)]),
    SectionSpec("Miglioramenti", [re.compile(r"miglior", re.IGNORECASE)]),
    SectionSpec("Fix necessari", [re.compile(r"fix", re.IGNORECASE)]),
]

SOURCE_ALIASES: Dict[str, str] = {
    "service_dirs": "taverna_saves",
    "cartelle_di_servizio": "taverna_saves",
}


def build_source_map() -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for path in MODULE_DIR.iterdir():
        key = normalise_name(path.stem if path.is_file() else path.name)
        mapping[key] = path
    return mapping


def resolve_source_path(
    module_label: str, source_map: Dict[str, Path]
) -> Optional[Path]:
    stem = normalise_name(module_label)
    stem = ALIASES.get(stem, stem)
    stem = SOURCE_ALIASES.get(stem, stem)
    return source_map.get(stem)


def extract_sections(lines: List[str]) -> List[SectionBlock]:
    heading_re = re.compile(r"^##\s+(.*)$")
    positions: List[tuple[int, str]] = []

    for idx, line in enumerate(lines):
        match = heading_re.match(line.strip())
        if match:
            positions.append((idx, match.group(1).strip()))

    blocks: List[SectionBlock] = []
    for current, (start, heading) in enumerate(positions):
        end = positions[current + 1][0] if current + 1 < len(positions) else len(lines)
        blocks.append(SectionBlock(heading=heading, start=start, end=end))
    return blocks


def has_content(lines: List[str], block: SectionBlock) -> bool:
    for line in lines[block.start + 1 : block.end]:
        if line.strip():
            return True
    return False


def has_bullet(lines: Iterable[str]) -> bool:
    return any(line.strip().startswith("- ") for line in lines)


def has_placeholder(lines: Iterable[str]) -> bool:
    return any(line.strip().lower().startswith(PLACEHOLDER.lower()) for line in lines)


def ensure_placeholder(lines: List[str], block: SectionBlock) -> None:
    insertion = block.end
    lines.insert(insertion, PLACEHOLDER)
    if insertion + 1 < len(lines) and lines[insertion + 1].strip():
        lines.insert(insertion + 1, "")


def ensure_section(
    lines: List[str], spec: SectionSpec, *, write: bool
) -> Optional[str]:
    blocks = extract_sections(lines)
    target: Optional[SectionBlock] = None
    for block in blocks:
        if spec.matches(block.heading):
            target = block
            break

    if target is None:
        if write:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"## {spec.title}")
            lines.append(PLACEHOLDER)
            lines.append("")
            return None
        return f"Sezione mancante: {spec.title}"

    if not has_content(lines, target):
        if write:
            ensure_placeholder(lines, target)
            return None
        return f"Sezione vuota: {target.heading}"

    section_lines = lines[target.start + 1 : target.end]
    if not has_bullet(section_lines):
        if write:
            ensure_placeholder(lines, target)
            return None
        return f"Nessun bullet in sezione: {target.heading}"

    if not write and has_placeholder(section_lines):
        return f"Segnaposto da sostituire in sezione: {target.heading}"

    return None


def create_report_skeleton(module_label: str) -> List[str]:
    lines = [f"# Report modulo `{module_label}`", ""]
    for spec in SECTION_SPECS:
        lines.append(f"## {spec.title}")
        lines.append(PLACEHOLDER)
        lines.append("")
    return lines


def process_report(
    module_label: str,
    report_map: Dict[str, Path],
    source_map: Dict[str, Path],
    *,
    write: bool,
) -> List[str]:
    issues: List[str] = []

    report_path = find_report(module_label, report_map)
    if not report_path:
        stem = ALIASES.get(normalise_name(module_label), normalise_name(module_label))
        report_path = REPORT_DIR / f"{stem}.md"

    source_path = resolve_source_path(module_label, source_map)
    if not source_path:
        print(
            f"[WARN] Sorgente non trovato per '{module_label}' in {MODULE_DIR}",
            file=sys.stderr,
        )

    if report_path.exists():
        lines = report_path.read_text(encoding="utf-8").splitlines()
    elif write:
        lines = create_report_skeleton(module_label)
    else:
        issues.append(f"Report mancante: {report_path.relative_to(REPO_ROOT)}")
        return issues

    original = list(lines)

    for spec in SECTION_SPECS:
        issue = ensure_section(lines, spec, write=write)
        if issue:
            issues.append(f"{report_path.relative_to(REPO_ROOT)} — {issue}")

    if write and lines != original:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print(f"Aggiornato: {report_path.relative_to(REPO_ROOT)}")

    return issues


def collect_extra_reports(
    sequence: Sequence[str], report_map: Dict[str, Path]
) -> List[Path]:
    sequence_stems = {
        ALIASES.get(normalise_name(label), normalise_name(label)) for label in sequence
    }
    extras = []
    for stem, path in report_map.items():
        if stem not in sequence_stems:
            extras.append(path)
    return extras


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize module reports with standard QA sections."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="Validate reports without modifying them"
    )
    mode.add_argument(
        "--write", action="store_true", help="Insert missing sections and placeholders"
    )
    args = parser.parse_args()

    sequence = load_sequence_from_guide()
    report_map = map_reports()
    source_map = build_source_map()

    all_issues: List[str] = []
    for label in sequence:
        all_issues.extend(
            process_report(
                label,
                report_map,
                source_map,
                write=args.write,
            )
        )

    for extra in collect_extra_reports(sequence, report_map):
        label = extra.stem
        all_issues.extend(
            process_report(label, report_map, source_map, write=args.write)
        )

    if args.check and all_issues:
        print("\n".join(all_issues), file=sys.stderr)
        return 1

    if args.check:
        print("Tutti i report includono le sezioni obbligatorie con almeno un bullet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
