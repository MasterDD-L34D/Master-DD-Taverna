#!/usr/bin/env python3
"""Lint legale per i cataloghi reference.

Verifica che i cataloghi OGC siano etichettati correttamente e non contengano
Product Identity nota, e che pi_local_only/ non sia tracciato da git.

Uso:
  python tools/legal_filter.py

Emette:
  - reports/legal_filter_report.json
  - reports/legal_filter_report.csv

Esce con codice != 0 in caso di violazioni bloccanti.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
MANIFEST_PATH = REFERENCE_DIR / "manifest.json"
REPORT_DIR = REPO_ROOT / "reports"
REPORT_JSON = REPORT_DIR / "legal_filter_report.json"
REPORT_CSV = REPORT_DIR / "legal_filter_report.csv"


# Product Identity nota di Paizo / Pathfinder 1E. I termini sono controllati con
# word boundary per ridurre i falsi positivi.
PI_WORDS = {
    # Setting
    "Golarion",
    "Absalom",
    "Varisia",
    "Cheliax",
    "Andoran",
    "Qadira",
    "Taldor",
    "Ustalav",
    "Numeria",
    "Osirion",
    "Katapesh",
    "Mana Wastes",
    "Thuvia",
    "Rahadoum",
    "Druma",
    "Kyonin",
    "Five Kings Mountains",
    "Hold of Belkzen",
    "Mammoth Lords",
    "Sodden Lands",
    "Stolen Lands",
    # Deità
    "Iomedae",
    "Desna",
    "Torag",
    "Sarenrae",
    "Cayden",
    "Pharasma",
    "Asmodeus",
    "Norgorber",
    "Calistria",
    "Shelyn",
    "Zon-Kuthon",
    "Irori",
    "Gorum",
    "Erastil",
    "Urgathoa",
    "Besmara",
    "Abadar",
    "Nethys",
    # Iconici
    "Seelah",
    "Ezren",
    "Valeros",
    "Merisiel",
    "Kyra",
    "Harsk",
    "Lem",
    "Sajan",
    "Amiri",
    "Lini",
    # Marchi / entità
    "Paizo",
}

# Frasi PI che vanno controllate come sottostringhe esatte (case-insensitive).
PI_PHRASES = {
    "Pathfinder Society",
    "Paizo Inc.",
    "Paizo Publishing",
}


def _load_manifest() -> Mapping:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest non trovato: {MANIFEST_PATH}")
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, Mapping) else {}


# Campi di contenuto OGC da scansionare per PI. I campi di provenienza
# (source, reference_urls, ...) sono esclusi perché possono contenere nomi di
# siti/marchi necessari per l'attribution tecnica.
SCANNED_FIELDS = {
    "name",
    "description",
    "short_description",
    "prerequisites",
    "requirements",
    "benefit",
    "special",
    "normal",
    "goal",
    "completion_benefit",
    "notes",
    "tags",
    "flavor",
}


def _iter_strings(obj, skip_metadata: bool = True):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_strings(item, skip_metadata=skip_metadata)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if skip_metadata and key in ("_license", "_source"):
                continue
            if skip_metadata and key not in SCANNED_FIELDS:
                continue
            yield from _iter_strings(value, skip_metadata=skip_metadata)


def _find_pi(text: str) -> list[dict]:
    """Restituisce le occorrenze PI trovate in text."""
    found = []
    lowered = text.lower()
    for phrase in PI_PHRASES:
        start = 0
        while True:
            idx = lowered.find(phrase.lower(), start)
            if idx == -1:
                break
            found.append({
                "type": "phrase",
                "term": phrase,
                "context": text[max(0, idx - 30) : idx + len(phrase) + 30],
            })
            start = idx + len(phrase)
    for word in PI_WORDS:
        for match in re.finditer(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE):
            found.append({
                "type": "word",
                "term": word,
                "context": text[max(0, match.start() - 30) : match.end() + 30],
            })
    return found


def _check_catalog_headers(catalog: Mapping, data: object) -> list[str]:
    """Verifica che un catalogo OGC abbia _license e _source."""
    errors = []
    if not isinstance(data, Mapping):
        errors.append("deve essere un oggetto JSON")
        return errors
    if "_license" not in data:
        errors.append("campo _license mancante")
    if "_source" not in data:
        errors.append("campo _source mancante")
    return errors


def _check_git_tracked_pi() -> list[str]:
    """Verifica che pi_local_only/ non contenga file tracciati da git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "data/reference/pi_local_only/"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return ["git non trovato; impossibile verificare pi_local_only"]
    tracked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    errors = []
    for path in tracked:
        if Path(path).name == ".gitkeep":
            continue
        errors.append(f"pi_local_only contiene file tracciato da git: {path}")
    return errors


def run() -> int:
    violations: list[dict] = []
    manifest = _load_manifest()
    catalogs = manifest.get("catalogs", [])

    for catalog in catalogs:
        if not isinstance(catalog, Mapping):
            continue
        rel_path = catalog.get("file", "")
        kind = catalog.get("kind") or Path(rel_path).stem

        # Cataloghi local_only non sono redistribuiti: non applichiamo i vincoli
        # di header OGC o scan PI su di essi. Il check git su pi_local_only/ e'
        # comunque eseguito piu' sotto.
        if catalog.get("local_only") or "pi_local_only" in rel_path:
            continue

        path = REFERENCE_DIR / rel_path

        if not path.exists():
            violations.append({
                "catalog": kind,
                "path": str(rel_path),
                "type": "missing_file",
                "detail": f"file dichiarato nel manifest non trovato: {path}",
            })
            continue

        data = json.loads(path.read_text(encoding="utf-8"))

        if catalog.get("is_ogc"):
            header_errors = _check_catalog_headers(catalog, data)
            for err in header_errors:
                violations.append({
                    "catalog": kind,
                    "path": str(rel_path),
                    "type": "missing_header",
                    "detail": err,
                })

            # Scansiona i testi per PI solo nei cataloghi OGC redistribuibili.
            entries = data.get("entries", []) if isinstance(data, dict) else data
            for text in _iter_strings(entries):
                for occurrence in _find_pi(text):
                    violations.append({
                        "catalog": kind,
                        "path": str(rel_path),
                        "type": "product_identity",
                        "term": occurrence["term"],
                        "term_type": occurrence["type"],
                        "context": occurrence["context"],
                    })

    for err in _check_git_tracked_pi():
        violations.append({
            "catalog": "pi_local_only",
            "path": "data/reference/pi_local_only/",
            "type": "git_tracked_pi",
            "detail": err,
        })

    summary = {
        "total_violations": len(violations),
        "by_type": {},
        "by_catalog": {},
    }
    for v in violations:
        summary["by_type"][v["type"]] = summary["by_type"].get(v["type"], 0) + 1
        summary["by_catalog"][v["catalog"]] = summary["by_catalog"].get(v["catalog"], 0) + 1

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "manifest": str(MANIFEST_PATH),
        "exit_code": 1 if violations else 0,
        "summary": summary,
        "violations": violations,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with REPORT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["catalog", "path", "type", "term", "term_type", "context", "detail"],
        )
        writer.writeheader()
        for v in violations:
            writer.writerow({
                "catalog": v.get("catalog", ""),
                "path": v.get("path", ""),
                "type": v.get("type", ""),
                "term": v.get("term", ""),
                "term_type": v.get("term_type", ""),
                "context": v.get("context", ""),
                "detail": v.get("detail", ""),
            })

    print(f"Violazioni rilevate: {len(violations)}")
    if violations:
        for v in violations[:20]:
            print(f"  [{v['type']}] {v['catalog']}: {v.get('detail') or v.get('term') or v.get('context', '')}")
        if len(violations) > 20:
            print(f"  ... e altre {len(violations) - 20} violazioni")
        print(f"Report salvato in: {REPORT_JSON}")
        return 1

    print(f"OK: nessuna violazione legale. Report salvato in: {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
