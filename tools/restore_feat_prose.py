#!/usr/bin/env python3
"""Ripristina la prosa corrotta dalla sanitize storica naive nelle 75 entry
feats dell'appendice di reports/pi_feats_triage.md (lotto 2026-07-25).

Fonte: pagine FeatDisplay AoN (fetch seriale 2s via reference_fetch, cache).
Convenzione catalogo (verificata sulle D del triage): description =
flavor + "\\n\\n" + Benefit (no etichette/Special); prerequisites da
split_prereq_string; references = ["Pathfinder PRD: <name>"]; source/tags/
source_id/reference_urls invariati; updated_at = oggi. Il testo ripristinato
e' sanitizzato (description=True) per riapplicare il masking PI sanctioned.

Default: dry-run. --write applica e scrive feats.json + report.
--offline: solo cache (fallisce su miss).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_fetch import cache_path, fetch
from tools.reference_lib import OGL_DIR, clean, split_prereq_string
from tools.sanitize_reference_pi import sanitize_text

ROOT = Path(__file__).resolve().parents[1]
FEATS_PATH = OGL_DIR / "feats.json"
REPORT_SRC = ROOT / "reports" / "pi_feats_triage.md"
REPORT_PATH = ROOT / "reports" / "restore_feat_prose.md"
BASE = "https://aonprd.com/FeatDisplay.aspx?ItemName="

# Grafie del catalogo (import storico d20pfsrd) -> nome canonico AoN moderno.
# Verificate una a una il 2026-07-25 (fetch + h1.title). Senza mappa AoN
# risponde con la pagina generica Feats (nessun h1.title).
NAME_VARIANTS = {
    "Aspiringnoble": "Aspiring Noble",
    "Bend With The Wind": "Bend with the Wind",
    "Eye For Ingredients": "Eye for Ingredients",
    "My Blade Is Yours": "My Blade is Yours",
    "Prosperity And Pride": "Prosperity and Pride",
    "Protector Of The People": "Protector of the People",
    "Touched By Sacred Fire": "Touched by Sacred Fire",
}

# Entry corrotte sfuggite all'appendice del triage (rilevate il 2026-07-25
# rieseguendo il rilevatore sistemico _systemic_corruption sui dati correnti):
# "visual ea bardents" (Harrowed Summoning), "Arcana barbarianum"
# (Supernatural Spy). Pagine AoN verificate.
SUPPLEMENTAL_NAMES = ["Harrowed Summoning", "Supernatural Spy"]

# Ripristino manuale dei 2 feat assenti da AoN moderno (decisione fonte
# 2026-07-25: testo OGL verbatim da d20pfsrd, che riporta il testo dei libri
# con la stessa dicitura; Spell Bluff confermato anche su legacy.aonprd.com
# ultimateMagicFeats). Convenzione identica al ripristino da FeatDisplay:
# description = flavor + "\n\n" + Benefit; references = "Pathfinder PRD: X".
MANUAL_RESTORE_TABLE = {
    "Spell Bluff": {
        "description": (
            "You know the principles of arcane dueling, and when fighting other "
            "spellcasters, you have learned to hide the true nature of your "
            "spells until the last possible moment.\n\n"
            "If another spellcaster tries to counterspell your casting, she "
            "adds +4 to her Spellcraft DC when trying to determine your spell. "
            "Because you have studied how to mask the recognizable elements of "
            "your spellcasting, you gain a +2 bonus on your Spellcraft checks "
            "to identify and counter an opponent's spell if it is a spell you "
            "know or have in your spellbook."
        ),
    },
    "Hindrance Dismissal": {
        "description": (
            "You've mastered the art of dismissing certain spells when they "
            "become a problem for you or your allies.\n\n"
            "You can dismiss any pit spell (such as create pit, hungry pit, "
            "spiked pit, and similar spells with 'pit' in their names) or wall "
            "spell (such as wall of fire, wall of ice, and similar spells with "
            "'wall' in their names) you cast. The spells must have a duration "
            "of at least 1 round. This ability follows the normal rules for "
            "dismissing spells, allowing you to dismiss conjured pits and "
            "walls as a standard action."
        ),
    },
}

_LABEL_RE = re.compile(
    r"^(Prerequisites?|Benefit|Normal|Special|Note|Goal|Completion Benefit|Suggested Traits)\s*:\s*(.*)$",
    re.I | re.S,
)
_LABEL_ONLY_RE = re.compile(
    r"^(Prerequisites?|Benefit|Normal|Special|Note|Goal|Completion Benefit|Suggested Traits)$",
    re.I,
)
_LEAD_COLON_RE = re.compile(r"^:\s*")
_PUNCT_ONLY_RE = re.compile(r"^[,;]+$")
_SRCLINE_RE = re.compile(r"^.*\bpg\.\s*\d+.*$")


def appendix_names() -> list[str]:
    """I 75 nomi dall'appendice del report triage (fonte di verita' committata)."""
    text = REPORT_SRC.read_text(encoding="utf-8")
    m = re.search(
        r"<details><summary>Elenco entry \(nomi\)</summary>\s*(.*?)\s*</details>",
        text,
        re.S,
    )
    if not m:
        sys.exit("ERRORE: appendice non trovata in " + str(REPORT_SRC))
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


def parse_feat_page(html: str) -> dict:
    """Pagina FeatDisplay -> {name, source, flavor, prerequisites, benefit}."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1", class_="title")
    if not h1:
        raise ValueError("h1.title non trovato (pagina non FeatDisplay?)")
    name = clean(h1.get_text())
    span = h1.parent
    source = ""
    src_b = span.find("b", string=lambda s: s and s.strip() == "Source")
    if src_b and src_b.find_next("i"):
        source = clean(src_b.find_next("i").get_text())
        source = re.sub(r"\s*pg\.\s*\d+.*$", "", source).strip()

    flavor_parts, benefit_parts, prereq_parts = [], [], []
    mode = "flavor"
    sources_seen = 0
    for seg in (clean(s) for s in span.stripped_strings):
        if seg == "Source":
            # La seconda occorrenza apre una sezione diversa (Mythic/Combat
            # Stamina/...): il feat base finisce qui.
            sources_seen += 1
            if sources_seen > 1:
                break
            continue
        if not seg or seg == name or _SRCLINE_RE.match(seg):
            continue
        label_m = _LABEL_ONLY_RE.match(seg)
        m = _LABEL_RE.match(seg)
        if _PUNCT_ONLY_RE.match(seg):
            continue
        if label_m:
            m_label = label_m.group(1).lower()
            rest = ""
        elif m:
            m_label = m.group(1).lower()
            rest = m.group(2).strip()
        else:
            m_label = None
            rest = ""
        if m_label is not None:
            if m_label.startswith("prerequisite"):
                mode = "prereq"
                if rest:
                    prereq_parts.append(rest)
            elif m_label == "benefit":
                mode = "benefit"
                if rest:
                    benefit_parts.append(rest)
            else:  # Normal / Special / Note / Goal / Completion Benefit / Suggested Traits
                mode = "skip"
            continue
        seg = _LEAD_COLON_RE.sub("", seg)
        if not seg:
            continue
        if mode == "flavor":
            flavor_parts.append(seg)
        elif mode == "prereq":
            prereq_parts.append(seg)
        elif mode == "benefit":
            benefit_parts.append(seg)
    prereq_text = clean(" ".join(prereq_parts))
    return {
        "name": name,
        "source": source,
        "flavor": clean(" ".join(flavor_parts)),
        "prerequisites": split_prereq_string(prereq_text) if prereq_text else [],
        "benefit": clean(" ".join(benefit_parts)),
    }


def apply_restore(entry: dict, page: dict) -> dict:
    """Aggiorna l'entry con i dati della pagina (convenzione catalogo)."""
    out = dict(entry)
    desc = (
        page["flavor"] + "\n\n" + page["benefit"] if page["flavor"] else page["benefit"]
    )
    out["description"] = sanitize_text(desc, description=True)
    out["prerequisites"] = [
        sanitize_text(p, description=True) for p in page["prerequisites"]
    ]
    out["references"] = [f"Pathfinder PRD: {entry['name']}"]
    out["updated_at"] = date.today().isoformat() + "T00:00:00Z"
    return out


def _fetch_page(name: str, offline: bool) -> str:
    aon_name = NAME_VARIANTS.get(name, name)
    url = BASE + aon_name.replace(" ", "%20").replace("'", "%27")
    if offline:
        path = cache_path(url)
        if not path.exists():
            raise FileNotFoundError(url)
        return path.read_text(encoding="utf-8", errors="replace")
    return fetch(url, delay=2.0, cache=True)


def cmd_manual(write: bool) -> int:
    """Modalita' --manual: applica MANUAL_RESTORE_TABLE (feat assenti da AoN
    moderno; testo OGL verificato da d20pfsrd/legacy AoN il 2026-07-25)."""
    catalog = json.loads(FEATS_PATH.read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in catalog["entries"]}
    applied = []
    for name, spec in MANUAL_RESTORE_TABLE.items():
        entry = by_name.get(name)
        if entry is None:
            sys.exit(f"ERRORE: {name} assente dal catalogo")
        entry["description"] = spec["description"]
        entry["references"] = [f"Pathfinder PRD: {name}"]
        entry["updated_at"] = date.today().isoformat() + "T00:00:00Z"
        applied.append(name)
    print(f"manual restore: {len(applied)} entry: {', '.join(applied)}")
    if write:
        FEATS_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Scritto: {FEATS_PATH}")
    else:
        print("Dry-run: nessuna modifica (usa --write)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument(
        "--manual",
        action="store_true",
        help="applica MANUAL_RESTORE_TABLE (feat assenti da AoN moderno)",
    )
    args = ap.parse_args(argv)

    if args.manual:
        return cmd_manual(args.write)

    names = appendix_names() + [
        n for n in SUPPLEMENTAL_NAMES if n not in appendix_names()
    ]
    catalog = json.loads(FEATS_PATH.read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in catalog["entries"]}
    missing = [n for n in names if n not in by_name]
    if missing:
        sys.exit(f"ERRORE: nomi appendice assenti dal catalogo: {missing}")

    restored, failures, src_mismatch = [], [], []
    for name in names:
        try:
            page = parse_feat_page(_fetch_page(name, args.offline))
        except Exception as exc:
            failures.append(f"- **{name}**: {exc}")
            continue
        entry = by_name[name]
        if page["source"] and entry.get("source") and page["source"] != entry["source"]:
            src_mismatch.append(
                f"- **{name}**: catalogo `{entry['source']}` vs pagina `{page['source']}`"
            )
        if not page["benefit"]:
            failures.append(
                f"- **{name}**: benefit vuoto (parse sospetto, entry non toccata)"
            )
            continue
        if args.write:
            entry.update(apply_restore(entry, page))
        restored.append(name)

    print(
        f"nomi: {len(names)}; ripristinati: {len(restored)}; falliti: {len(failures)}"
    )
    for line in failures:
        print(line)
    for line in src_mismatch:
        print(line)
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        return 0

    FEATS_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = (
        [
            "# Ripristino prosa feats (2026-07-25)",
            "",
            f"- Entry in appendice: {len(names)}",
            f"- Ripristinate: {len(restored)}",
            f"- Fallite (404/parse): {len(failures)}",
            "",
            "## Fallite",
            "",
        ]
        + (failures or ["(nessuna)"])
        + ["", "## Mismatch source catalogo/pagina (non bloccanti)", ""]
        + (src_mismatch or ["(nessuno)"])
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Scritto: {FEATS_PATH}; report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
