"""Test synthetic good/bad per tools/check_instruction_guards.py.

Stile PR #276 vault: niente fixture su disco — documenti buoni/cattivi in
memoria; un caso per controllare che ciascun guard separi davvero il drift.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from check_instruction_guards import CHECKS, evaluate

RELS = [rel for _, rel, _, _ in CHECKS]

GOOD_AGENTS = """\
# AGENTS.md
- **Local-first**: nessuna dipendenza da API esterne per il flusso principale.
- Commit: trailer `Coding-Agent:` + `Trace-Id:` su ogni commit; MAI `Co-Authored-By:`.
- `data/reference/pi_local_only/` (Product Identity, **solo locale, mai committare**).
"""

GOOD_INTERPRETER = """\
# docstring
I verbi senza helper restano NO_OP (mai competenza finta), log backlog.
if saltati:  # evento aggregato: il merge parziale e' mai silenzioso
"""

GOOD_ROUTER = """\
Le flag di pipeline sono NO_OP motivate — mai competenza finta (RZ1).
"""

GOOD_DECISIONS = "\n".join(
    [
        "## ADR 008 — Update parziale: semantica merge nei comandi del DSL",
        "## ADR 009 — Archivio sessione: store KV unico su file",
        "## ADR 010 — Verbo `export`: persistenza dell'ultimo output",
        "## ADR 011 — Namespace comandi: collisioni rendicontate",
        "## ADR 012 — `goto_state` eseguibile",
        "## ADR 013 — Verbi dominio: zucchero generico su helper",
        "## ADR 014 — Wizard input routing: run_input",
        "## ADR 015 — Router input libero: regex deterministico",
    ]
)


def good_docs():
    return {
        "AGENTS.md": GOOD_AGENTS,
        "src/dsl/interpreter.py": GOOD_INTERPRETER,
        "src/dsl/router.py": GOOD_ROUTER,
        "planning/decisions.md": GOOD_DECISIONS,
    }


def test_tutti_good_passano():
    results = evaluate(good_docs())
    assert all(results.values()), [n for n, ok in results.items() if not ok]


def test_adr_perso_fallisce():
    docs = good_docs()
    docs["planning/decisions.md"] = GOOD_DECISIONS.replace("## ADR 013", "## X")
    assert evaluate(docs)["decisions_adr_009_015"] is False


def test_competenza_finta_cancellata_fallisce():
    docs = good_docs()
    docs["src/dsl/router.py"] = "Le flag di pipeline sono NO_OP motivate."
    assert evaluate(docs)["router_rz1"] is False


def test_coauthored_tornato_fallisce():
    docs = good_docs()
    docs["AGENTS.md"] = GOOD_AGENTS + "\nCo-Authored-By: Claude\n"
    assert evaluate(docs)["agents_no_coauthored"] is False


def test_file_mancante_fallisce():
    docs = good_docs()
    del docs["AGENTS.md"]
    results = evaluate(docs)
    assert all(
        results[n] is False for n in results if n.startswith("agents_")
    )
    assert results["router_rz1"] is True  # i doc presenti restano validi
