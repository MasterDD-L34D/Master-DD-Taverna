#!/usr/bin/env python3
"""Lint legale per i cataloghi reference.

Verifica che i cataloghi OGC siano etichettati correttamente e non contengano
Product Identity nota, e che pi_local_only/ non sia tracciato da git.

Estensione 2026-07-19 (Task 3, planning/2026-07-19-pi-feats-triage.md):
la lista PI estesa (`PI_TERMS`, 75 termini, da tools/triage_pi_feats.py)
vive QUI come fonte unica — il triage la importa, niente doppie liste.
Il gate scansiona l'unione di: PI_TERMS, i termini storici del gate non
presenti nel triage feats (iconici, marchi, altri luoghi) e i candidati a
zero hit documentati nel triage (§ Copertura: toponimi sicuri + demon
lord/archdevil, a protezione degli import futuri). Match word-boundary
case-insensitive su regex unica (senza boundary "Nex" matcha "next").
I replacement sanctioned della sanitize (es. "the inner sea region", che
contiene "inner sea") sono mascherati prima della scansione — precedente:
tools/apply_pi_feats_policy.py (_masked_terms). "Sargava" resta fuori per
decisione documentata (hit solo come titolo libro in source/source_id).

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sanitize_reference_pi import DESCRIPTION_ONLY_REPLACEMENTS, REPLACEMENTS


REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
MANIFEST_PATH = REFERENCE_DIR / "manifest.json"
REPORT_DIR = REPO_ROOT / "reports"
REPORT_JSON = REPORT_DIR / "legal_filter_report.json"
REPORT_CSV = REPORT_DIR / "legal_filter_report.csv"


# Lista termini PI estesa (75), FONTE UNICA: importata da
# tools/triage_pi_feats.py (Task 3). Word-boundary obbligatorio (senza
# boundary "Nex" matcha "next" — motivo dei 227 falsi positivi della
# scansione grezza del triage). Estensione 2026-07-19 (quality review):
# +21 termini verificati a mano — 17 da review piu' Hermean, Kellid, Mzali,
# Vudra da sweep word-boundary su feats.json. Falsi positivi scartati
# documentati nel report di triage (Shackles, Linnorm, Juju).
PI_TERMS = [
    # Nazioni / regioni / luoghi di Golarion
    "Golarion", "Absalom", "Varisia", "Cheliax", "Chelaxian", "Taldor",
    "Taldan", "Andoran", "Andoren", "Qadira", "Qadiran", "Osirion",
    "Osirian", "Osiriani", "Nex", "Geb", "Nidal", "Rahadoum", "Rahadoumi",
    "Thuvia", "Thuvian", "Katapesh", "Kyonin", "Druma", "Numeria",
    "Ustalav", "Oppara", "Sodden Lands", "Mana Wastes", "Inner Sea",
    # Deita' maggiori
    "Sarenrae", "Iomedae", "Asmodeus", "Desna", "Calistria", "Norgorber",
    "Zon-Kuthon", "Urgathoa", "Rovagug", "Lamashtu", "Abadar", "Irori",
    "Gozreh", "Pharasma", "Shelyn", "Cayden", "Erastil", "Torag",
    "Besmara", "Gorum", "Nethys",
    # Organizzazioni / ordini
    "Aldori", "Hellknight", "Pathfinder Society",
    # Toponimi / etnie / deita' minori Golarion (estensione quality review)
    "Lastwall", "Worldwound", "Belkzen", "Shoanti", "Mwangi", "Tian",
    "Varisian", "Chelish", "Irrisen", "Galt", "Hermea", "Hermean",
    "Alkenstar", "Korvosa", "Riddleport", "Daggermark", "River Kingdoms",
    "Walkena", "Mzali", "Vudra", "Kellid",
]

# Sottoinsieme delle deita': il triage lo usa per la categoria B
# (prerequisito deita-specifico). Fonte unica anche per questo set.
DEITY_TERMS = {
    "sarenrae", "iomedae", "asmodeus", "desna", "calistria", "norgorber",
    "zon-kuthon", "urgathoa", "rovagug", "lamashtu", "abadar", "irori",
    "gozreh", "pharasma", "shelyn", "cayden", "erastil", "torag",
    "besmara", "gorum", "nethys", "walkena",
}

# Termini storici del gate (pre-Task 3) non presenti nel triage feats:
# iconici, marchi e altri luoghi Golarion-specifici.
GATE_LEGACY_TERMS = {
    # Luoghi
    "Five Kings Mountains", "Hold of Belkzen", "Mammoth Lords",
    "Stolen Lands", "Azlant", "Azlanti", "Thassilon", "Thassilonian",
    # Iconici
    "Seelah", "Ezren", "Valeros", "Merisiel", "Kyra", "Harsk", "Lem",
    "Sajan", "Amiri", "Lini",
    # Marchi / entita'
    "Paizo",
}

# Candidati a zero hit sul catalogo corrente (triage 2026-07-19, § Copertura
# della lista): toponimi sicuri + demon lord/archdevil. Inclusi a protezione
# degli import futuri; a zero hit oggi non creano violazioni.
# NOTA: "Sargava" NON e' in lista per decisione documentata (hit solo come
# titolo libro in source/source_id; la policy sui titoli libro e' separata).
# "Azlant"/"Thassilon" erano gia' tra i termini storici del gate.
# "Osiria" (variante di "Osirion") aggiunta in quality review Task 3: aveva
# 1 hit reale (prereq di Bureaucrat's Favored), sanitizzato con la famiglia
# Osirion; resta nel gate a protezione degli import futuri.
GATE_CANDIDATE_TERMS = {
    # Toponimi sicuri
    "Magnimar", "Nirmathas", "Molthune", "Brevoy", "Sandpoint", "Cassomir",
    "Ostenso", "Westcrown", "Egorian", "Almas", "Sothis", "Mendev",
    "Sarkoris", "Vudran", "Jalmeray", "Iobaria", "Kalabuto", "Bloodcove",
    "Eleder", "Usaro", "Garund", "Avistan", "Mbeke", "Taralu", "Xin",
    "Aroden", "Osiria",
    # Demon lord / archdevil
    "Deskari", "Baphomet", "Pazuzu", "Nocticula", "Zura", "Cyth-V'sug",
    "Moloch", "Belial", "Dispater", "Mammon", "Geryon", "Baalzebul",
    "Mephistopheles",
}

# Product Identity scansionata dal gate: unione delle tre liste sopra.
# I termini sono controllati con word boundary per ridurre i falsi positivi.
PI_WORDS = set(PI_TERMS) | GATE_LEGACY_TERMS | GATE_CANDIDATE_TERMS

# Frasi PI che vanno controllate come sottostringhe esatte (case-insensitive).
# "Pathfinder Society" non e' qui: e' in PI_TERMS (word-boundary la copre;
# tenerla in entrambe raddoppierebbe i hit).
PI_PHRASES = {
    "Paizo Inc.",
    "Paizo Publishing",
}

# Regex unica delle parole PI: termini piu' lunghi prima (es. "Hold of
# Belkzen" prima di "Belkzen"), word-boundary su entrambi i lati,
# case-insensitive (stessa tecnica della regex del triage).
_PI_WORDS_RE = re.compile(
    r"\b(?P<term>" + "|".join(
        re.escape(w) for w in sorted(PI_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Forma canonica del termine (quella della lista) per i hit: la regex e'
# case-insensitive, il report usa la forma della lista.
_CANONICAL = {w.lower(): w for w in PI_WORDS}

# Replacement sanctioned della sanitize che contengono ancora un termine PI
# letterale (oggi solo "the inner sea region", che contiene "inner sea"):
# mascherati prima della scansione, come in apply_pi_feats_policy. Derivati
# dalle liste di REPLACEMENTS (fonte unica): se un futuro replacement
# contenesse un termine PI, entrerebbe automaticamente nel mask.
_SANCTIONED_MASK = [
    re.compile(re.escape(value), re.IGNORECASE)
    for value in sorted(
        {new for _, new in REPLACEMENTS + DESCRIPTION_ONLY_REPLACEMENTS
         if _PI_WORDS_RE.search(new)},
        key=len, reverse=True)
]


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
    """Restituisce le occorrenze PI trovate in text.

    I replacement sanctioned della sanitize (es. "the inner sea region") sono
    mascherati prima della scansione: contengono un termine PI letterale ma
    sono testo legittimo prodotto dalla sanitize stessa.
    """
    for mask_re in _SANCTIONED_MASK:
        text = mask_re.sub("", text)
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
    for match in _PI_WORDS_RE.finditer(text):
        found.append({
            "type": "word",
            "term": _CANONICAL.get(match.group("term").lower(), match.group("term")),
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
