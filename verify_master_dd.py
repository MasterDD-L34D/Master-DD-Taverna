#!/usr/bin/env python3
"""Verifica automatica del lavoro su Master-DD-Pathfinder-GPT."""
import json
import os
import subprocess
import sys
from pathlib import Path


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
    if "130 passed" not in out or "1 skipped" not in out:
        sys.exit("ERRORE: test suite non conforme (atteso 130 passed, 1 skipped)")
    print("OK: pytest -> 130 passed, 1 skipped")


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


def check_rag_index():
    store_dir = Path("src/data/vector_store")
    if not (store_dir / "chunks.json").exists() or not (store_dir / "embeddings.npy").exists():
        sys.exit("ERRORE: indice RAG non trovato in src/data/vector_store")
    chunks = json.load(open(store_dir / "chunks.json", encoding="utf-8"))
    if len(chunks) < 5000:
        sys.exit(f"ERRORE: indice RAG troppo piccolo ({len(chunks)} chunk)")
    print(f"OK: indice RAG pronto con {len(chunks)} chunk")


def check_rag_endpoints():
    from fastapi.testclient import TestClient
    from src.app import app
    from src.config import settings
    from src.rag.store import VectorStore

    store_dir = Path("src/data/vector_store")
    if not VectorStore(store_dir).is_ready():
        print("SKIP: endpoint RAG non testati per indice mancante")
        return

    original_key = settings.api_key
    original_allow = settings.allow_anonymous
    try:
        settings.api_key = "verify-rag-key"
        settings.allow_anonymous = False
        headers = {"x-api-key": "verify-rag-key"}
        with TestClient(app) as client:
            resp = client.post("/rag/search", json={"query": "talento Power Attack", "top_k": 3}, headers=headers)
            if resp.status_code != 200:
                sys.exit(f"ERRORE: /rag/search ha risposto {resp.status_code}: {resp.text}")
            data = resp.json()
            if len(data.get("results", [])) != 3:
                sys.exit("ERRORE: /rag/search non ha restituito 3 risultati")

            resp = client.post("/rag/ask", json={"query": "cosa fa Power Attack?", "top_k": 3, "provider": "mock"}, headers=headers)
            if resp.status_code != 200:
                sys.exit(f"ERRORE: /rag/ask ha risposto {resp.status_code}: {resp.text}")
        print("OK: endpoint RAG /search e /ask funzionanti")
    finally:
        settings.api_key = original_key
        settings.allow_anonymous = original_allow


def check_build_endpoint():
    from fastapi.testclient import TestClient
    from src.app import app
    from src.config import settings
    from src.rag.store import VectorStore

    store_dir = Path("src/data/vector_store")
    if not VectorStore(store_dir).is_ready():
        print("SKIP: endpoint /rag/build non testato per indice mancante")
        return

    original_key = settings.api_key
    original_allow = settings.allow_anonymous
    try:
        settings.api_key = "verify-build-key"
        settings.allow_anonymous = False
        headers = {"x-api-key": "verify-build-key"}
        with TestClient(app) as client:
            resp = client.post(
                "/rag/build",
                json={"class": "Fighter", "race": "Human", "level": 5, "focus": "DPR", "provider": "mock"},
                headers=headers,
            )
            if resp.status_code != 200:
                sys.exit(f"ERRORE: /rag/build ha risposto {resp.status_code}: {resp.text}")
            data = resp.json()
            if "build" not in data or data["build"]["build_state"]["class"] != "Fighter":
                sys.exit("ERRORE: /rag/build non ha restituito una build valida")
        print("OK: endpoint /rag/build funzionante")
    finally:
        settings.api_key = original_key
        settings.allow_anonymous = original_allow


def main():
    check_pytest()
    check_validate_schemas()
    check_data_quality_report()
    check_orphans()
    check_module_index()
    check_reports_valid_json()
    check_rag_index()
    check_rag_endpoints()
    check_build_endpoint()
    print("\n=== VERIFICA Master-DD-Pathfinder-GPT: TUTTO OK ===")


if __name__ == "__main__":
    main()
