#!/usr/bin/env python3
"""Importa gli archetipi delle classi del catalogo dagli indici AoN
(Archetypes.aspx?Class=<Classe>): tabella curata Name/Replaces/Summary con
marcatori razziali '(X Only)'. Lotto 2 archetipi 2026-07-25.

Policy (spec grilling 2026-07-25, adattamento tabella-indice confermato):
- solo le pagine indice (24 classi di classes.json); i dettagli per-capacita'
  (alters/level/testo completo da ArchetypeDisplay) sono lotto futuro;
- race_req dai marcatori '(X Only)' nella tabella (copre razze non-core);
- archetypes.json riscritto in schema standard (header preservato);
- nomi con identita' PI -> pi_local_only/archetypes_local.json (verbatim);
  description sanitizzata (description=True); gate legal_filter = 0;
- manifest aggiornato (files.archetypes + catalogs archetypes/archetypes_local).

Default: dry-run. --write applica. --offline usa solo la cache (no rete).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.expand_spells_gist import is_pi_name
from tools.reference_fetch import cache_path, fetch
from tools.reference_lib import OGL_DIR, clean, slug, source_id
from tools.sanitize_reference_pi import sanitize_text

ROOT = Path(__file__).resolve().parents[1]
ARCHETYPES_PATH = OGL_DIR / "archetypes.json"
CLASSES_PATH = OGL_DIR / "classes.json"
LOCAL_PATH = ROOT / "data" / "reference" / "pi_local_only" / "archetypes_local.json"
MANIFEST_PATH = ROOT / "data" / "reference" / "manifest.json"
REPORT_PATH = ROOT / "reports" / "import_archetypes.md"
BASE = "https://aonprd.com/"

_RACE_ONLY_RE = re.compile(r"\(([^()]+?)\s+[Oo]nly\)")

_LEVEL_RE = re.compile(r"\bAt (\d+)(?:st|nd|rd|th) level")
_REPLACES_RE = re.compile(r"(?i)this ability (?:also )?replaces? (?:the )?([^.]+)\.")
_ALTERS_RE = re.compile(r"(?i)this ability (?:also )?alters? (?:the )?([^.]+)\.")
_FEAT_SUFFIX_RE = re.compile(r"\s*\((?:Ex|Su|Sp)\)\s*$")


def _split_feature_list(text):
    """'armor training 1 and weapon training 2' -> ['armor training 1', 'weapon training 2'].
    Espansione suffissi numerici: 'armor training 1, 2, 3, and 4' ->
    ['armor training 1', 'armor training 2', 'armor training 3', 'armor training 4']."""
    text = re.sub(r"(?i)\s+class features?\.?$", "", text.strip())
    text = re.sub(r"(?i)\s+ability\.?$", "", text)
    parts = [
        p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", text) if p.strip()
    ]
    out = []
    for p in parts:
        if out and re.match(r"^\d+(?:st|nd|rd|th)?$", p):
            base = re.match(r"^(.*?)\s*\d+(?:st|nd|rd|th)?$", out[-1])
            out.append(f"{base.group(1)} {p}" if base else p)
        else:
            out.append(p)
    return out


def parse_archetype_features(html):
    """Pagina ArchetypeDisplay: [{name, level, replaces, alters, text}].

    Feature = '<b>Nome (Ex|Su|Sp)</b>:' + prosa fino alla feature successiva.
    level = primo 'At Nth level'; replaces/alters dalle frasi 'This ability
    replaces/alters X'. Flavor introduttivo saltato (prima del primo <b>
    non-Source)."""
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1", class_="title")
    if not h1:
        return []
    container = h1.parent
    feats, current, parts = [], None, []

    def flush():
        if current:
            text = clean(" ".join(p for p in parts if p)).lstrip(": ")
            m = _LEVEL_RE.search(text)
            rep = _REPLACES_RE.search(text)
            alt = _ALTERS_RE.search(text)
            feats.append(
                {
                    "name": current,
                    "level": int(m.group(1)) if m else None,
                    "replaces": _split_feature_list(rep.group(1)) if rep else [],
                    "alters": _split_feature_list(alt.group(1)) if alt else [],
                    "text": sanitize_text(text, description=True),
                }
            )

    for el in container.descendants:
        name_attr = getattr(el, "name", None)
        if name_attr == "b":
            t = clean(el.get_text())
            if t and t != "Source":
                flush()
                current, parts = _FEAT_SUFFIX_RE.sub("", t), []
            continue
        if isinstance(el, NavigableString) and el.parent.name not in (
            "b",
            "i",
            "a",
            "h1",
            "h2",
            "h3",
            "sup",
            "script",
            "style",
        ):
            if current:
                parts.append(clean(str(el)))
    flush()
    return feats


def parse_archetypes(html: str) -> list[dict]:
    """Tabella Name/Replaces/Summary -> [{name, replaces, race_req, summary, detail_url}]."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        headers = [clean(c.get_text()) for c in trs[0].find_all(["th", "td"])]
        if headers[:3] != ["Name", "Replaces", "Summary"]:
            continue
        rows = []
        for tr in trs[1:]:
            cells = tr.find_all(["th", "td"], recursive=False)
            if len(cells) != 3:
                continue
            name = clean(cells[0].get_text())
            link = cells[0].find("a")
            detail_url = None
            if link and link.get("href"):
                href = link["href"]
                if not href.startswith("http"):
                    href = BASE + href
                detail_url = href.replace(" ", "%20")
            raw_replaces = clean(cells[1].get_text())
            raw_summary = clean(cells[2].get_text())
            blob = f"{raw_replaces} {raw_summary}"
            raw_races = set(_RACE_ONLY_RE.findall(blob))
            # Marcatori compositi '(X and Y Only)' -> requisiti separati
            # (semantica OR: l'archetipo e' prendibile da ciascuna razza).
            race_req = (
                sorted({r for raw in raw_races for r in raw.split(" and ")}) or None
            )
            summary = clean(_RACE_ONLY_RE.sub("", raw_summary))
            replaces = [
                r.strip()
                for r in _RACE_ONLY_RE.sub("", raw_replaces).split(";")
                if r.strip()
            ]
            rows.append(
                {
                    "name": name,
                    "replaces": replaces,
                    "race_req": race_req,
                    "summary": summary,
                    "detail_url": detail_url,
                }
            )
        return rows
    return []


def archetype_entry(row: dict, class_name: str) -> dict:
    """Riga parsata -> entry catalogo standard (description sanitizzata)."""
    tags = ["archetype", slug(class_name), slug(row["name"]).replace("_", "-")]
    if row["race_req"]:
        tags += [f"race:{slug(r)}" for r in row["race_req"]]
    return {
        "name": row["name"],
        "source": "Archives of Nethys (aonprd.com)",
        "source_id": source_id("archetype", f"{class_name} {row['name']}"),
        "prerequisites": [],
        "tags": tags,
        "references": [f"AoN: {class_name} Archetypes"],
        "reference_urls": (
            [f"{BASE}Archetypes.aspx?Class={class_name.replace(' ', '%20')}"]
            + ([row["detail_url"]] if row["detail_url"] else [])
        ),
        "description": sanitize_text(row["summary"], description=True),
        "mechanics": {
            "class": class_name,
            "replaces": row["replaces"],
            "race_req": row["race_req"],
        },
    }


def catalog_classes() -> list[str]:
    data = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    return [e["name"] for e in data["entries"]]


def _fetch_class(url: str, offline: bool) -> str:
    """HTML della pagina indice; in --offline solo cache (mai rete)."""
    if offline:
        path = cache_path(url)
        if not path.exists():
            raise FileNotFoundError(f"non in cache: {url}")
        return path.read_text(encoding="utf-8", errors="replace")
    return fetch(url, delay=2.0, cache=True)


def _enrich_details(write: bool, offline: bool) -> int:
    """Modalità --details: aggiunge mechanics.features (da ArchetypeDisplay)
    alle entry esistenti di archetypes.json + archetypes_local.json.

    I dettagli arrivano da reference_urls[1] (detail_url, gia' nel catalogo);
    i count non cambiano (manifest invariato). Report features senza level."""
    no_level = 0
    total_feats = 0
    failures = []
    for path in (ARCHETYPES_PATH, LOCAL_PATH):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        for e in catalog["entries"]:
            if len(e.get("reference_urls", [])) < 2:
                failures.append(f"- **{e['name']}**: detail_url assente")
                continue
            url = e["reference_urls"][1]
            try:
                html = _fetch_class(url, offline)
            except Exception as exc:
                failures.append(f"- **{e['name']}**: {exc}")
                continue
            feats = parse_archetype_features(html)
            if not feats:
                failures.append(f"- **{e['name']}**: 0 features parsate")
            e["mechanics"]["features"] = feats
            total_feats += len(feats)
            no_level += sum(1 for f in feats if f["level"] is None)
        if write:
            path.write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    print(
        f"features: {total_feats} totali ({no_level} senza level); "
        f"anomalie: {len(failures)}"
    )
    for line in failures[:30]:
        print(line)
    if not write:
        print("Dry-run: nessuna modifica (usa --write)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="fallisce se una pagina non e' in cache (nessuna rete)",
    )
    ap.add_argument(
        "--details",
        action="store_true",
        help="arricchisce le entry esistenti con mechanics.features "
        "da ArchetypeDisplay (nessun re-import da indice)",
    )
    args = ap.parse_args(argv)

    if args.details:
        return _enrich_details(args.write, args.offline)

    classes = catalog_classes()
    all_entries, local_entries, report = [], [], []
    for cls in classes:
        url = f"{BASE}Archetypes.aspx?Class={cls.replace(' ', '%20')}"
        try:
            html = _fetch_class(url, args.offline)
        except Exception as exc:  # rete giu' o pagina assente
            report.append(f"- **{cls}**: FETCH FALLITO ({exc})")
            continue
        rows = parse_archetypes(html)
        n_racial = sum(1 for r in rows if r["race_req"])
        n_zero = sum(1 for r in rows if not r["replaces"])
        report.append(
            f"- **{cls}**: {len(rows)} archetipi "
            f"({n_racial} razziali, {n_zero} senza replaces)"
        )
        for row in rows:
            entry = archetype_entry(row, cls)
            (local_entries if is_pi_name(entry["name"]) else all_entries).append(entry)

    total = len(all_entries) + len(local_entries)
    print(
        f"classi: {len(classes)}; archetipi: {total} "
        f"(OGL {len(all_entries)}, PI->local {len(local_entries)})"
    )
    print("\n".join(report))
    if not args.write:
        print("Dry-run: nessuna modifica (usa --write)")
        for e in local_entries[:20]:
            print(f"  PI local: {e['mechanics']['class']} / {e['name']}")
        return 0

    catalog = json.loads(ARCHETYPES_PATH.read_text(encoding="utf-8"))
    catalog["entries"] = all_entries
    ARCHETYPES_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    local_catalog = {
        "_license": "OGL-1.0a",
        "_source": "Archives of Nethys (local only, not redistributed)",
        "entries": local_entries,
    }
    LOCAL_PATH.write_text(
        json.dumps(local_catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    manifest["files"]["archetypes"]["entries"] = len(all_entries)
    for c in manifest["catalogs"]:
        if c["kind"] == "archetypes":
            c["entries"] = len(all_entries)
            c["last_verified"] = today
            c["notes"] = (
                "Archetipi da indici AoN per classe (tabella "
                "Name/Replaces/Summary): mechanics {class, replaces, "
                "race_req}. Rigenerare con tools/import_archetypes.py."
            )
    manifest["catalogs"] = [
        c for c in manifest["catalogs"] if c["kind"] != "archetypes_local"
    ]
    if local_entries:
        manifest["catalogs"].append(
            {
                "file": "pi_local_only/archetypes_local.json",
                "kind": "archetypes_local",
                "source": "Archives of Nethys (aonprd.com)",
                "license": "OGL-1.0a",
                "is_ogc": False,
                "is_pi": False,
                "cup_allowed": False,
                "local_only": True,
                "entries": len(local_entries),
                "notes": (
                    "Archetipi con Product Identity nel nome, separati dal "
                    "catalogo OGL (policy 2026-07-25). NON redistribuire."
                ),
                "last_verified": today,
            }
        )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = (
        [
            "# Import archetipi da indici AoN (2026-07-25)",
            "",
            f"- Classi: {len(classes)}",
            f"- Archetipi totali: {total}",
            f"- OGL (archetypes.json): {len(all_entries)}",
            f"- PI -> archetypes_local.json: {len(local_entries)}",
            "",
            "## Conteggi per classe",
            "",
        ]
        + report
        + ["", "## Nomi PI spostati in locale", ""]
    )
    lines += [f"- {e['mechanics']['class']} / {e['name']}" for e in local_entries]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Scritto: {ARCHETYPES_PATH} ({len(all_entries)} entry)")
    print(f"Scritto: {LOCAL_PATH} ({len(local_entries)} entry, NON committare)")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
