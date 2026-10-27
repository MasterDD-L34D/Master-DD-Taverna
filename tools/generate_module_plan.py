#!/usr/bin/env python3
"""Generate a per-module work plan from module reports.

The script follows the sequence defined in `planning/module_review_guide.md`
(“Sequenza di lettura”) and extracts tasks from each report in
`reports/module_tests/`. For every module it collects:
- Fix necessari → prioritised as P1 (bug/ambiguità funzionali)
- Miglioramenti → default P2 (QA/completezza) unless a bullet is tagged with
  `[P3]` or another explicit priority prefix
- Errori → added as contextual notes per modulo

It also emits a closing summary with task counts and highest priority per
modulo, and highlights the cross-cutting clusters (builder/bilanciamento e
hub/persistenza) menzionati nella guida.

Usage:
    python tools/generate_module_plan.py --output planning/module_work_plan.md

If a report is missing, the entry will be flagged as "Report mancante".
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE_PATH = REPO_ROOT / "planning" / "module_review_guide.md"
REPORT_DIR = REPO_ROOT / "reports" / "module_tests"
DEFAULT_OUTPUT = REPO_ROOT / "planning" / "module_work_plan.md"
DEFAULT_EXECUTIVE_OUTPUT = REPO_ROOT / "planning" / "executive_work_plan.md"

# Mapping for guide labels that do not match report stems
ALIASES: Dict[str, str] = {
    "cartelle_di_servizio": "service_dirs",
}

SEQUENCE_FALLBACK = [
    "Encounter_Designer",
    "Taverna_NPC",
    "adventurer_ledger",
    "archivist",
    "base_profile",
    "explain_methods",
    "knowledge_pack",
    "meta_doc",
    "minmax_builder",
    "narrative_flow",
    "ruling_expert",
    "scheda_pg_markdown_template",
    "sigilli_runner_module",
    "tavern_hub",
    "Cartelle di servizio",
]

BUILDER_CLUSTER = {"encounter_designer", "minmax_builder"}
HUB_CLUSTER = {"taverna_npc", "tavern_hub", "cartelle_di_servizio"}


@dataclass
class ModuleSummary:
    label: str
    report_path: Optional[Path]
    tasks: List[Tuple[int, str]]
    errors: List[str]
    observations: List[str]
    dependencies: List[str]

    @property
    def status(self) -> str:
        if not self.report_path or not self.report_path.exists():
            return "In attesa (aggiungere report)"
        if self.tasks:
            return "Pronto per sviluppo"
        return "In attesa (nessun task rilevato)"

    @property
    def highest_priority(self) -> str:
        if not self.tasks:
            return "N/A"
        level = min(p for p, _ in self.tasks)
        return f"P{level}"


def normalise_name(name: str) -> str:
    """Normalise a module label into a comparable stem."""
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    return stem


def load_sequence_from_guide() -> List[str]:
    pattern = re.compile(r"^\d+\.\s+(.*)")
    lines = GUIDE_PATH.read_text(encoding="utf-8").splitlines()
    sequence = []
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            sequence.append(match.group(1).strip())
    return sequence or SEQUENCE_FALLBACK


def map_reports() -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for report in REPORT_DIR.glob("*.md"):
        mapping[report.stem.lower()] = report
    return mapping


def find_report(module_label: str, existing: Dict[str, Path]) -> Optional[Path]:
    stem = normalise_name(module_label)
    stem = ALIASES.get(stem, stem)
    return existing.get(stem)


def parse_sections(lines: List[str]) -> List[Tuple[str, List[str]]]:
    """Return a list of (heading, content_lines) pairs for level-2 sections."""

    sections: List[Tuple[str, List[str]]] = []
    heading_re = re.compile(r"^##\s+(.*)$")
    current_heading: Optional[str] = None
    buffer: List[str] = []

    for line in lines:
        match = heading_re.match(line.strip())
        if match:
            if current_heading is not None:
                sections.append((current_heading, buffer))
            current_heading = match.group(1).strip()
            buffer = []
            continue
        if current_heading is not None:
            buffer.append(line.rstrip())

    if current_heading is not None:
        sections.append((current_heading, buffer))

    return sections


def parse_bullets(lines: Iterable[str]) -> List[str]:
    bullets: List[str] = []
    current: List[str] = []
    for line in lines:
        if line.startswith("- "):
            if current:
                bullets.append(" ".join(current).strip())
            current = [line[2:].strip()]
        elif current:
            current.append(line.strip())
    if current:
        bullets.append(" ".join(current).strip())
    return bullets


def parse_prioritised_tasks(
    lines: List[str], *, default_priority: int
) -> List[Tuple[int, str]]:
    tasks: List[Tuple[int, str]] = []
    for bullet in parse_bullets(lines):
        match = re.match(r"^\[P(\d)\]\s+(.*)", bullet)
        if match:
            priority = int(match.group(1))
            text = match.group(2).strip()
        else:
            priority = default_priority
            text = bullet
        tasks.append((priority, text))
    return tasks


def collect_section_lines(
    sections: Sequence[Tuple[str, List[str]]], patterns: Sequence[re.Pattern[str]]
) -> List[str]:
    """
    Return the concatenated content lines for all sections whose heading matches
    any of the provided patterns (case-insensitive, supports combined headings
    and emoji). The order of matching sections is preserved and multiple
    matching sections are combined.
    """

    matching_sections: List[List[str]] = []
    for heading, content in sections:
        if any(pattern.search(heading) for pattern in patterns):
            matching_sections.append(content)

    merged_lines: List[str] = []
    for idx, content in enumerate(matching_sections):
        if idx and (not merged_lines or merged_lines[-1] != ""):
            merged_lines.append("")
        merged_lines.extend(content)

    return merged_lines


def summarise_module(module_label: str, report_path: Optional[Path]) -> ModuleSummary:
    if not report_path or not report_path.exists():
        return ModuleSummary(module_label, report_path, [], [], [], [])

    lines = report_path.read_text(encoding="utf-8").splitlines()
    sections = parse_sections(lines)

    error_patterns = [re.compile(r"errori", re.IGNORECASE)]
    improvement_patterns = [
        re.compile(r"migliorament", re.IGNORECASE),
        re.compile(r"note\s+e\s+miglioramenti", re.IGNORECASE),
    ]
    observation_patterns = [
        re.compile(r"osservazion", re.IGNORECASE),
        re.compile(r"note\s+e\s+osservazioni", re.IGNORECASE),
    ]
    dependency_patterns = [re.compile(r"dipendenze", re.IGNORECASE)]
    fix_patterns = [re.compile(r"fix\s+necessari", re.IGNORECASE)]

    fix_lines = collect_section_lines(sections, fix_patterns)
    improvement_lines = collect_section_lines(sections, improvement_patterns)
    error_lines = collect_section_lines(sections, error_patterns)
    observation_lines = collect_section_lines(sections, observation_patterns)
    dependency_lines = collect_section_lines(sections, dependency_patterns)

    fixes = parse_prioritised_tasks(fix_lines, default_priority=1)
    improvements = parse_prioritised_tasks(improvement_lines, default_priority=2)
    errors = parse_bullets(error_lines)
    observations = parse_bullets(observation_lines)
    dependencies = parse_bullets(dependency_lines)

    tasks: List[Tuple[int, str]] = fixes + improvements
    return ModuleSummary(
        module_label, report_path, tasks, errors, observations, dependencies
    )


def format_module_block(summary: ModuleSummary) -> str:
    report_text = (
        "**mancante**"
        if not summary.report_path
        else f"`{summary.report_path.relative_to(REPO_ROOT)}`"
    )
    parts = [
        f"## {summary.label}",
        f"- Report: {report_text}",
        f"- Stato: {summary.status}",
        "",
        "### Task (priorità e scope)",
    ]

    if summary.tasks:
        for priority, text in sorted(summary.tasks, key=lambda t: t[0]):
            parts.append(f"- [P{priority}] {text}")
    else:
        parts.append("- Nessun task rilevato")

    parts.extend(["", "### Dipendenze"])
    if summary.dependencies:
        parts.extend([f"- {item}" for item in summary.dependencies])
    else:
        parts.append("- Nessuna dipendenza esplicita")

    parts.extend(["", "### Note (Osservazioni/Errori)"])
    if summary.observations or summary.errors:
        parts.extend([f"- [Osservazione] {item}" for item in summary.observations])
        parts.extend([f"- [Errore] {item}" for item in summary.errors])
    else:
        parts.append("- Nessuna nota aggiuntiva")

    parts.append("")
    return "\n".join(parts)


def _sequence_index_map(sequence: Sequence[str]) -> Dict[str, int]:
    return {label: idx for idx, label in enumerate(sequence)}


def _module_sort_key(
    module_label: str, *, sequence_index: Dict[str, int]
) -> Tuple[int, int, str]:
    stem = normalise_name(module_label)
    cluster_rank = 0 if stem in BUILDER_CLUSTER else 1 if stem in HUB_CLUSTER else 2
    return (cluster_rank, sequence_index.get(module_label, 999), stem)


def build_executive_plan(
    summaries: Sequence[ModuleSummary],
    *,
    sequence: Sequence[str],
    executive_output: Path,
) -> None:
    sequence_index = _sequence_index_map(sequence)

    tasks_by_priority: Dict[int, List[Tuple[str, str]]] = {1: [], 2: [], 3: []}
    for summary in summaries:
        for priority, text in summary.tasks:
            tasks_by_priority.setdefault(priority, []).append((summary.label, text))

    def format_phase(
        title: str,
        items: List[Tuple[str, str]],
    ) -> List[str]:
        lines: List[str] = [f"## {title}", ""]
        if not items:
            lines.append("- Nessun task aperto")
            lines.append("")
            return lines

        grouped: Dict[str, List[str]] = {}
        for module, task in items:
            grouped.setdefault(module, []).append(task)

        for module in sorted(
            grouped, key=lambda m: _module_sort_key(m, sequence_index=sequence_index)
        ):
            lines.append(f"- **{module}**")
            for task in grouped[module]:
                lines.append(f"  - {task}")
        lines.append("")
        return lines

    now = dt.datetime.now(dt.timezone.utc)
    header = [
        "# Piano di lavoro esecutivo",
        "",
        f"Generato il {now.isoformat(timespec='seconds').replace('+00:00', 'Z')} da `tools/generate_module_plan.py`",
        "Fonte task: `planning/module_work_plan.md` (priorità P1→P3) e sequenza `planning/module_review_guide.md`.",
        "Obiettivo: coprire tutte le azioni fino al completamento del piano operativo, con fasi sequenziali e dipendenze esplicite.",
        "",
        "### Regole di ordinamento",
        "- Prima i cluster critici: builder/bilanciamento (Encounter_Designer, minmax_builder) e hub/persistenza (Taverna_NPC, tavern_hub, Cartelle di servizio).",
        "- All'interno del cluster, ordine di lettura della guida; poi priorità (P1→P3).",
        "",
    ]

    phase1 = format_phase(
        "Fase 1 (attuale) · P1 critici e cross-cutting", tasks_by_priority.get(1, [])
    )
    phase2 = format_phase(
        "Seconda fase · P1 residui e P2 cooperativi",
        tasks_by_priority.get(2, []),
    )
    phase3 = format_phase(
        "Terza fase · Rifiniture P3, doc e chiusura backlog",
        tasks_by_priority.get(3, []),
    )

    tracking = [
        "### Tracciamento avanzamento",
        "| Modulo | Task aperti | Osservazioni | Errori | Dipendenze | Priorità massima | Stato |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for summary in sorted(
        summaries,
        key=lambda s: _module_sort_key(s.label, sequence_index=sequence_index),
    ):
        tracking.append(
            "| "
            f"{summary.label} | {len(summary.tasks)} | {len(summary.observations)} | "
            f"{len(summary.errors)} | {len(summary.dependencies)} | {summary.highest_priority} | {summary.status} |"
        )

    executive_output.parent.mkdir(parents=True, exist_ok=True)
    executive_output.write_text(
        "\n".join(header + phase1 + phase2 + phase3 + tracking), encoding="utf-8"
    )


def build_plan(output_path: Path, executive_output: Path) -> None:
    sequence = load_sequence_from_guide()
    sequence_index = _sequence_index_map(sequence)
    report_map = map_reports()

    summaries: List[ModuleSummary] = []
    for module in sequence:
        report_path = find_report(module, report_map)
        summaries.append(summarise_module(module, report_path))

    now = dt.datetime.now(dt.timezone.utc)
    header = [
        "# Piano operativo generato dai report",
        "",
        f"Generato il {now.isoformat(timespec='seconds').replace('+00:00', 'Z')}",
        "Fonte sequenza: `planning/module_review_guide.md`",
        "",
        "## Checklist seguita (dal documento di guida)",
        "- Sequenza completa: Encounter_Designer → Taverna_NPC → adventurer_ledger → archivist → base_profile → explain_methods → knowledge_pack → meta_doc → minmax_builder → narrative_flow → ruling_expert → scheda_pg_markdown_template → sigilli_runner_module → tavern_hub → Cartelle di servizio.",
        "- Per ogni report: checklist Ambiente di test → Esiti API → Metadati → Comandi/Flow → QA → Errori → Miglioramenti → Fix necessari.",
        "- Task derivati da Errori/Fix/Miglioramenti con priorità P1 bug/ambiguità, P2 QA/completezza, P3 UX/copy; collegare a sezioni/linee citate nei report.",
        "- Stato modulo: Pronto per sviluppo se i task sono completi e scoped; In attesa se servono dati aggiuntivi.",
        "- Cross-cutting: coordinare builder/bilanciamento (Encounter_Designer, minmax_builder) e hub/persistenza (Taverna_NPC, tavern_hub, Cartelle di servizio).",
        "",
    ]

    body = [format_module_block(summary) for summary in summaries]

    note_summary = [
        "## Riepilogo osservazioni ed errori",
        "| Modulo | Osservazioni | Errori | Totale note |",
        "| --- | --- | --- | --- |",
    ]
    for summary in sorted(
        summaries,
        key=lambda item: (len(item.observations) + len(item.errors)),
        reverse=True,
    ):
        note_summary.append(
            "| "
            f"{summary.label} | {len(summary.observations)} | {len(summary.errors)} | "
            f"{len(summary.observations) + len(summary.errors)} |"
        )

    cross_cutting = [
        "## Cross-cutting e dipendenze",
        "- Builder/Bilanciamento (Encounter_Designer, minmax_builder): usare i task sopra per valutare epic condivise su export/QA o flow di bilanciamento; ordinare i fix P1 prima dei miglioramenti.",
        "- Hub/Persistenza (Taverna_NPC, tavern_hub, Cartelle di servizio): verificare coerenza delle policy di salvataggio/quarantena e annotare eventuali blocchi prima di procedere con altri moduli dipendenti.",
        "",
        "## Chiusura",
        "- Compila il sommario sprint con numero task, priorità massima e blocchi per modulo usando la tabella seguente.",
        "",
    ]

    summary_columns = [
        "Modulo",
        "Task totali",
        "Priorità massima",
        "#Dipendenze",
        "Stato",
        "#Osservazioni",
        "#Errori",
    ]
    summary_rows = [
        "| " + " | ".join(summary_columns) + " |",
        "| " + " | ".join(["---"] * len(summary_columns)) + " |",
    ]
    for summary in sorted(
        summaries,
        key=lambda s: _module_sort_key(s.label, sequence_index=sequence_index),
    ):
        row_cells = [
            summary.label,
            str(len(summary.tasks)),
            summary.highest_priority,
            str(len(summary.dependencies)),
            summary.status,
            str(len(summary.observations)),
            str(len(summary.errors)),
        ]
        summary_rows.append("| " + " | ".join(row_cells) + " |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(header + body + note_summary + cross_cutting + summary_rows),
        encoding="utf-8",
    )

    build_executive_plan(
        summaries,
        sequence=sequence,
        executive_output=executive_output,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a work plan from module reports."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the output Markdown file (default: planning/module_work_plan.md)",
    )
    parser.add_argument(
        "--executive-output",
        type=Path,
        default=DEFAULT_EXECUTIVE_OUTPUT,
        help="Path to the executive plan Markdown file (default: planning/executive_work_plan.md)",
    )
    args = parser.parse_args()
    build_plan(args.output, args.executive_output)
    print(f"Work plan written to {args.output}")
    print(f"Executive plan written to {args.executive_output}")
