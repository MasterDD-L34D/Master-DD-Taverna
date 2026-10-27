from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

DEFAULT_CHANGELOG = Path("reports/changelog_2025-12-26.md")
DEFAULT_PYTEST_LOG = Path("reports/qa_log.md")
DEFAULT_ATTESTATO = Path("reports/coverage_attestato_2025-12-11.md")
DEFAULT_TIMELINE = Path("reports/release_timeline.md")


def build_message(
    release_date: str,
    changelog: Path,
    rc_status: str,
    pytest_log: Path,
    attestato: Path,
) -> str:
    header = f"## Annuncio rilascio {release_date}"
    body = [
        "- Changelog: " + changelog.as_posix(),
        "- Tag/branch RC: " + rc_status,
        "- Log QA 2025-12-11: " + pytest_log.as_posix(),
        "- Attestato automatico: " + attestato.as_posix(),
        "\nFeedback/approvazioni: <inserisci breve nota dopo la pubblicazione>.",
    ]
    return "\n".join([header, "", *body]) + "\n\n"


def write_message(output_path: Path, content: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def append_timeline(
    timeline_path: Path,
    release_date: str,
    message_path: Path,
    rc_status: str,
    feedback_note: str,
) -> None:
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Timeline rilasci\n\n"
    existing_content = header
    if timeline_path.exists():
        existing_content = timeline_path.read_text(encoding="utf-8")

    lines = existing_content.splitlines()
    filtered: list[str] = []
    skip = False
    marker = f"## {release_date}"
    for line in lines:
        if line == marker:
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            filtered.append(line)

    entry = [
        marker,
        f"- Messaggio: {message_path.as_posix()}",
        f"- Tag/branch RC: {rc_status}",
        f"- Feedback/approvazioni: {feedback_note or 'TODO dopo pubblicazione'}",
        "",
    ]
    updated_content = "\n".join(filtered).rstrip() + "\n\n" + "\n".join(entry)
    timeline_path.write_text(updated_content + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara annuncio e timeline di rilascio"
    )
    parser.add_argument(
        "--date",
        dest="release_date",
        default=date.today().isoformat(),
        help="Data ISO del rilascio",
    )
    parser.add_argument(
        "--rc-status",
        dest="rc_status",
        default="Da creare",
        help="Stato del tag/branch RC",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help="Percorso al changelog",
    )
    parser.add_argument(
        "--pytest-log",
        dest="pytest_log",
        type=Path,
        default=DEFAULT_PYTEST_LOG,
        help="Percorso al log pytest 11/12",
    )
    parser.add_argument(
        "--attestato",
        type=Path,
        default=DEFAULT_ATTESTATO,
        help="Percorso all'attestato automatico",
    )
    parser.add_argument(
        "--output", type=Path, help="File di output per il messaggio di rilascio"
    )
    parser.add_argument(
        "--timeline",
        type=Path,
        default=DEFAULT_TIMELINE,
        help="File markdown della timeline di rilascio da aggiornare",
    )
    parser.add_argument(
        "--feedback",
        default="",
        help="Nota breve con feedback/approvazioni (può essere aggiunta dopo aver pubblicato il messaggio)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    release_date = args.release_date
    rc_status = args.rc_status
    changelog = args.changelog
    pytest_log = args.pytest_log
    attestato = args.attestato
    output_path = args.output or Path(f"reports/release_announcement_{release_date}.md")

    message = build_message(release_date, changelog, rc_status, pytest_log, attestato)
    write_message(output_path, message)
    append_timeline(args.timeline, release_date, output_path, rc_status, args.feedback)

    print("Messaggio pronto in:", output_path)
    print("Timeline aggiornata:", args.timeline)


if __name__ == "__main__":
    main()
