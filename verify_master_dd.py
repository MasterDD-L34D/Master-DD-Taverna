#!/usr/bin/env python3
"""Verifica automatica del lavoro su Master-DD-Pathfinder-GPT."""
import json
import os
import subprocess
import sys


def run(cmd, check=True):
    print(f"\n>>> {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    if check and res.returncode != 0:
        sys.exit(f"Comando fallito con exit code {res.returncode}")
    return res


def check_pytest():
    res = run([".venv/Scripts/python", "-m", "pytest", "-q"])
    out = res.stdout + res.stderr
    if "104 passed" not in out or "1 skipped" not in out:
        sys.exit("ERRORE: test suite non conforme (atteso 104 passed, 1 skipped)")
    print("OK: pytest -> 104 passed, 1 skipped")


def check_validate_schemas():
    res = run([".venv/Scripts/python", "tools/validate_schemas.py"], check=False)
    if res.returncode != 0:
        sys.exit("ERRORE: validate_schemas.py ha fallito")
    print("OK: validate_schemas.py -> terminato senza errori")


def check_data_quality_report():
    res = run([".venv/Scripts/python", "tools/data_quality_report.py"], check=False)
    if res.returncode != 0:
        sys.exit("ERRORE: data_quality_report.py ha crashato")
    out = res.stdout + res.stderr
    if "minmax_builder.txt" in out and "error" in out.lower():
        sys.exit("ERRORE: minmax_builder.txt ancora segnalato come errore")
    print("OK: data_quality_report.py -> completato, minmax_builder.txt OK")


def check_orphans():
    bak_dir = "src/data/builds/archive"
    baks = [f for f in os.listdir(bak_dir) if f.endswith(".bak")] if os.path.isdir(bak_dir) else []
    if baks:
        sys.exit(f"ERRORE: file .bak orfani presenti: {baks}")
    if os.path.exists("reports/module_tests/staging_sandbox_log.md"):
        sys.exit("ERRORE: report orfano staging_sandbox_log.md ancora presente")
    print("OK: nessun file .bak orfano, nessun report orfano")


def check_module_index():
    path = "src/data/module_index.json"
    data = json.load(open(path, encoding="utf-8"))
    entries = data.get("entries", [])
    for rec in entries:
        if rec.get("module") == "minmax_builder.txt":
            if rec.get("status") == "error" or rec.get("file") is None:
                sys.exit(f"ERRORE: minmax_builder.txt ancora corrotto: {rec}")
            print("OK: minmax_builder.txt entry corretta")
            return
    sys.exit("ERRORE: minmax_builder.txt non trovato in module_index.json")


def check_reports_valid_json():
    for name in ["reports/build_review.json", "reports/index_analysis.json", "reports/dual_pass_report.json", "reports/data_quality_report.json"]:
        if not os.path.exists(name):
            sys.exit(f"ERRORE: report mancante {name}")
        try:
            json.load(open(name, encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"ERRORE: {name} non è JSON valido: {e}")
    print("OK: tutti i report principali sono JSON validi")


def main():
    check_pytest()
    check_validate_schemas()
    check_data_quality_report()
    check_orphans()
    check_module_index()
    check_reports_valid_json()
    print("\n=== VERIFICA Master-DD-Pathfinder-GPT: TUTTO OK ===")


if __name__ == "__main__":
    main()
