"""Test per tools/oracle_three_way.py (REF-07: da spike a tool versionato).

Copre:
- le normalizzazioni pure (`_norm_name`, `_canon`, `_sheet_scores`,
  `_flex_choice`, `_compare`);
- la classificazione degli esiti (CONCORDE/DIVERGE/classi difetto corpus/
  TAVERNA_ERR) su dump sintetico ermetico (cataloghi e builder
  monkeypatchati, niente IO reale);
- il contratto CLI: default read-only (non scrive), `--write` rigenera
  report + registry, `--check` exit 0/1 sul drift del registry;
- smoke sulla catena reale (dump pathmaster-dd presente): nessun esito
  inatteso (ERROR/TAVERNA_ERR/classi difetto) — skip se il dump manca.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.oracle_three_way as ot

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- helpers


def _rec(file, abilities=None, v1=None, v2=None, **draft_kw):
    draft = {
        "name": file,
        "race": "Human",
        "class": "Fighter",
        "feats": [],
        "baseAbilities": abilities
        or {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 10, "cha": 8},
        "sheetAbilities": None,
        "flexDeclared": None,
    }
    draft.update(draft_kw)
    return {
        "file": file,
        "draft": draft,
        "v1": v1,
        "v2": v2,
        "v1Error": None,
        "v2Error": None,
    }


def _sheet(**over):
    sheet = {
        "errors": [],
        "hp": 12,
        "bab": 1,
        "initiative": 1,
        "saves": {"fort": 4, "ref": 1, "will": 0},
        "abilities": {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 8},
    }
    sheet.update(over)
    return sheet


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """IO e dipendenze esterne isolate: dump/report/registry in tmp_path,
    cataloghi e builder monkeypatchati. Ritorna una factory run(dump, argv)."""
    monkeypatch.setattr(ot, "DUMP_PATH", tmp_path / "dump.json")
    monkeypatch.setattr(ot, "REPORT_PATH", tmp_path / "report.md")
    monkeypatch.setattr(ot, "DEFECTS_PATH", tmp_path / "defects.json")
    monkeypatch.setattr(ot, "_race_mods", lambda race: (race, {}))
    monkeypatch.setattr(ot, "_canon", lambda path, name: name)
    sheets = {}

    def fake_build(draft):
        value = sheets[draft.name]
        if isinstance(value, Exception):
            raise value
        return value

    import src.pc.engine

    monkeypatch.setattr(src.pc.engine, "build_character", fake_build)

    def run(dump, argv=()):
        by_file = {r["file"]: r for r in dump if not r.get("error")}
        for file, sheet in sheets.items():
            assert file in by_file, f"sheet registrata per file assente: {file}"
        ot.DUMP_PATH.write_text(json.dumps(dump), encoding="utf-8")
        return ot.main(list(argv))

    run.sheets = sheets
    run.report_path = tmp_path / "report.md"
    run.defects_path = tmp_path / "defects.json"
    return run


# ------------------------------------------------------------ funzioni pure


def test_norm_name():
    assert ot._norm_name("Half Orc") == ot._norm_name("half-orc")
    assert ot._norm_name("Halfelf") == ot._norm_name("Half-Elf")
    assert ot._norm_name("  Arcanist ") == "arcanist"


def test_canon(tmp_path):
    catalog = tmp_path / "races.json"
    catalog.write_text(
        json.dumps({"entries": [{"name": "Half-Orc"}, {"name": "Strix"}]}),
        encoding="utf-8",
    )
    assert ot._canon(catalog, "half orc") == "Half-Orc"
    assert ot._canon(catalog, "STRIX") == "Strix"
    assert ot._canon(catalog, "Gnomo") is None


def test_sheet_scores():
    assert ot._sheet_scores(None) is None
    assert ot._sheet_scores(
        {"FOR": 16, "DES": 12, "COS": 14, "INT": 10, "SAG": 10, "CAR": 8}
    ) == {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 8}
    assert ot._sheet_scores({"FOR": "16", "altro": 3}) is None


def test_flex_choice():
    base = {"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 10, "cha": 8}
    sheet = dict(base, con=15)
    assert ot._flex_choice(base, {"any": 2}, sheet) == "con"
    assert ot._flex_choice(base, {"any": 2}, dict(base, con=16)) is None
    assert ot._flex_choice(base, {"any": 2}, None) is None


def test_compare():
    sheet = _sheet()
    diffs = []
    ot._compare(
        sheet,
        {
            "hp": 12,
            "bab": 1,
            "fort": 4,
            "ref": 1,
            "will": 0,
            "abilities": sheet["abilities"],
        },
        "vX",
        diffs,
    )
    assert diffs == []
    ot._compare(
        sheet,
        {
            "hp": 99,
            "bab": None,
            "fort": 2,
            "ref": None,
            "will": 0,
            "abilities": {"str": 10},
        },
        "vX",
        diffs,
    )
    # hp e fort divergono; bab/ref None = campo non calcolato (non divergenza);
    # abilities riporta solo str: si confronta solo quella.
    assert diffs == [
        "vX hp: taverna 12 vs 99",
        "vX fort: taverna 4 vs 2",
        "vX str: taverna 16 vs 10",
    ]
    diffs = []
    ot._compare(sheet, None, "vX", diffs)
    assert diffs == []  # motore assente: mai divergenza


# -------------------------------------------------- classificazione esiti


def test_status_concorde_e_diverge(harness, capsys):
    harness.sheets.update({"a.json": _sheet(), "b.json": _sheet()})
    dump = [
        _rec("a.json", v2={"hp": 12}),
        _rec("b.json", v2={"hp": 99}),
    ]
    assert harness(dump) == 0
    out = capsys.readouterr().out
    assert "Concorde a tre: 1. Divergenze: 1. Errori: 0." in out
    assert "| b | DIVERGE | v2 hp: taverna 12 vs 99 |" in out
    # Default read-only: niente file scritti.
    assert not harness.report_path.exists()
    assert not harness.defects_path.exists()


def test_status_error_dal_dump(harness, capsys):
    harness([{"file": "rotta.json", "error": "convert fail"}])
    out = capsys.readouterr().out
    assert "| rotta | ERROR | convert fail |" in out


def test_status_fuori_budget(harness, capsys):
    dump = [
        _rec(
            "ricca.json",
            abilities={
                "str": 18,
                "dex": 18,
                "con": 18,
                "int": 18,
                "wis": 18,
                "cha": 18,
            },
        )
    ]
    harness(dump)
    out = capsys.readouterr().out
    assert "| ricca | FUORI_BUDGET_GPT | point-buy 102 > 25" in out


def test_status_classi_difetto_dal_builder(harness, capsys):
    harness.sheets.update(
        {
            "feat.json": _sheet(errors=["feat: 4 selezionati su 2 consentiti al lv1"]),
            "prereq.json": _sheet(
                errors=["talento Arma accurata: prerequisito non soddisfatto (BAB +1)"]
            ),
            "flex.json": _sheet(errors=["race_bonus_ability obbligatorio per Human"]),
            "altra.json": _sheet(errors=["errore non classificato"]),
        }
    )
    harness([_rec(f) for f in ("feat.json", "prereq.json", "flex.json", "altra.json")])
    out = capsys.readouterr().out
    assert "| feat | FEAT_ILLEGALE_GPT |" in out
    assert "| prereq | PREREQ_ILLEGALE_GPT |" in out
    assert "| flex | FLEX_INDETERMINATO |" in out
    assert "| altra | TAVERNA_ERR |" in out


def test_status_taverna_err_su_eccezione(harness, capsys):
    harness.sheets["boom.json"] = ValueError("draft illegale")
    harness([_rec("boom.json")])
    out = capsys.readouterr().out
    assert "| boom | TAVERNA_ERR | draft illegale |" in out


def test_flex_dichiarato_e_invalido(harness, capsys, monkeypatch):
    monkeypatch.setattr(ot, "_race_mods", lambda race: (race, {"any": 2}))
    harness.sheets.update({"ok.json": _sheet(), "bad.json": _sheet()})
    dump = [
        _rec("ok.json", flexDeclared="COS"),
        _rec("bad.json", flexDeclared="XYZ"),
    ]
    harness(dump)
    out = capsys.readouterr().out
    assert "| ok | CONCORDE |" in out
    assert "| bad | TAVERNA_ERR | bonus_razziale_flessibile non valido: XYZ |" in out


# ------------------------------------------------------------------ CLI I/O


def test_write_rigenera_report_e_registry(harness):
    harness.sheets.update(
        {
            "sana.json": _sheet(),
            "feat.json": _sheet(errors=["feat: 4 selezionati su 2 consentiti al lv1"]),
        }
    )
    dump = [
        _rec("sana.json", v2={"hp": 12}),
        _rec("feat.json"),
        _rec(
            "ricca.json",
            abilities={
                "str": 18,
                "dex": 18,
                "con": 18,
                "int": 18,
                "wis": 18,
                "cha": 18,
            },
        ),
    ]
    assert harness(dump, ["--write"]) == 0
    report = harness.report_path.read_text(encoding="utf-8")
    assert report.startswith("# Oracolo a tre vie")
    assert "Build base: 3." in report
    registry = json.loads(harness.defects_path.read_text(encoding="utf-8"))
    assert registry["defects"]["feat.json"]["classes"] == ["feat_count_oltre_raw"]
    assert registry["defects"]["ricca.json"]["classes"] == ["stats_oltre_point_buy"]
    assert "sana.json" not in registry["defects"]


def test_check_ok_e_drift(harness, capsys):
    harness.sheets["sana.json"] = _sheet()
    dump = [_rec("sana.json", v2={"hp": 12})]
    # Senza registry su disco: drift (exit 1), e niente scritture.
    assert harness(dump, ["--check"]) == 1
    assert not harness.defects_path.exists()
    assert harness(dump, ["--write"]) == 0
    # Registry allineato: exit 0, nessuna modifica ai file.
    before = harness.defects_path.read_text(encoding="utf-8")
    assert harness(dump, ["--check"]) == 0
    assert harness.defects_path.read_text(encoding="utf-8") == before
    capsys.readouterr()
    # Drift: registry manomesso.
    harness.defects_path.write_text(
        json.dumps({"defects": {"x.json": {}}}), encoding="utf-8"
    )
    assert harness(dump, ["--check"]) == 1
    assert "CHECK FALLITO" in capsys.readouterr().out


def test_check_e_write_mutuamente_esclusivi(harness):
    with pytest.raises(SystemExit):
        harness([_rec("a.json")], ["--check", "--write"])


# ------------------------------------------------- smoke sulla catena reale


def test_catena_reale_nessun_esito_inatteso(capsys):
    """Smoke: il dump reale (28 build base, post lotto A/ENG-19) non produce
    esiti inattesi. Le divergenze v1 residue sono dichiarate (WORKFLOW
    par.5.1) e non pinnate qui: questo test vincola solo gli stati che
    alimenterebbero il registry difetti."""
    if not ot.DUMP_PATH.exists():
        pytest.skip("dump pathmaster-dd non presente (catena non rilanciata)")
    assert ot.main([]) == 0
    out = capsys.readouterr().out
    # La riga di sommario e' calcolata sulle righe complete (mai troncata):
    # "Errori: 0" garantisce assenza di ERROR/TAVERNA_ERR e di tutte le
    # classi difetto corpus (FUORI_BUDGET/FEAT_ILLEGALE/PREREQ/FLEX).
    assert "Errori: 0." in out
