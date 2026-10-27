"""Guard di regressione sulle istruzioni e sulle decisioni del repo.

Pattern PR #276 MasterDD-L34D/vault: controlli presenza/ausenza di frasi
canoniche sui documenti che governano agenti e metodo. Un drift qui (ADR
persi, principi "mai competenza finta"/"mai silenzioso" cancellati, vincoli
legali ammorbiditi) e' il tipo di regressione che i test del codice non
vedono. Uso: python tools/check_instruction_guards.py [--root PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ADR_RICHIESTI = [
    "## ADR 009",
    "## ADR 010",
    "## ADR 011",
    "## ADR 012",
    "## ADR 013",
    "## ADR 014",
    "## ADR 015",
]

# (nome, percorso relativo al root, frasi che devono esserci, frasi vietate)
CHECKS = [
    (
        "agents_no_coauthored",
        "AGENTS.md",
        ["MAI `Co-Authored-By:`"],
        ["Co-Authored-By: kimi", "Co-Authored-By: Claude"],
    ),
    (
        "agents_trailer_commit",
        "AGENTS.md",
        ["Coding-Agent:", "Trace-Id:"],
        [],
    ),
    (
        "agents_pi_mai_committare",
        "AGENTS.md",
        ["pi_local_only", "mai committare"],
        [],
    ),
    (
        "agents_local_first",
        "AGENTS.md",
        ["Local-first"],
        [],
    ),
    (
        "interpreter_mai_competenza_finta",
        "src/dsl/interpreter.py",
        ["mai competenza finta"],
        [],
    ),
    (
        "interpreter_mai_silenzioso",
        "src/dsl/interpreter.py",
        ["mai silenzioso"],
        [],
    ),
    (
        "router_rz1",
        "src/dsl/router.py",
        ["mai competenza finta (RZ1)"],
        [],
    ),
    (
        "decisions_adr_009_015",
        "planning/decisions.md",
        ADR_RICHIESTI,
        [],
    ),
]


def evaluate(docs: dict[str, str]) -> dict[str, bool]:
    """docs: percorso relativo -> testo. Restituisce nome -> pass/fail."""
    out = {}
    for name, rel, must, banned in CHECKS:
        text = docs.get(rel, "")
        out[name] = all(m in text for m in must) and all(b not in text for b in banned)
    return out


def load_documents(root: Path) -> dict[str, str]:
    return {rel: (root / rel).read_text(encoding="utf-8") for _, rel, _, _ in CHECKS}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="Root del repo")
    args = parser.parse_args(argv)
    root = args.root or Path(__file__).resolve().parent.parent
    results = evaluate(load_documents(root))
    failed = [n for n, ok in results.items() if not ok]
    for name, ok in results.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if failed:
        print(f"{len(failed)} guard falliti")
        return 1
    print(f"{len(results)} guard passati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
