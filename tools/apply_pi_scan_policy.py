#!/usr/bin/env python3
"""Applica la policy PI A/B/C ai termini dello scan con modello locale.

Scan 2026-11-02 (gemma4:e4b): i termini nuovi vivono in
tools/legal_filter.py (GATE_LLM_SCAN_TERMS). Stessa disciplina di
tools/apply_pi_traits_equipment_policy.py, ma la classificazione e' derivata
dal gate invece che da liste scritte a mano:

  A -- PI nel NOME -> spostamento verbatim in pi_local_only.
  B -- PI nei prerequisiti -> pi_local_only.
  C -- PI solo nel testo (description, tags, ...) -> sanitize in place.
"""

from __future__ import annotations

import json
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.legal_filter import SCANNED_FIELDS, _find_pi
from tools.sanitize_reference_pi import sanitize_text


def _hit_fields(entry):
    fields = set()
    for field, value in entry.items():
        if field not in SCANNED_FIELDS:
            continue
        for text in value if isinstance(value, list) else [value]:
            if isinstance(text, str) and _find_pi(text):
                fields.add(field)
    return fields


def classify(entry):
    """'A' (nome), 'B' (prerequisiti), 'C' (solo testo) o None (pulita)."""
    fields = _hit_fields(entry)
    if not fields:
        return None
    if "name" in fields:
        return "A"
    if "prerequisites" in fields:
        return "B"
    return "C"


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "data" / "reference"

LOCAL_HEADER = {
    "_license": "OGL-1.0a",
    "_source": "Archives of Nethys (aonprd.com) -- voci PI spostate dal catalogo "
    "OGL (scan PI con modello locale 2026-11-02); local only, not redistributed",
}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path, payload):
    # LF come i file committati: write_text su Windows convertirebbe in CRLF.
    path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def _key(entry):
    return entry.get("source_id") or entry.get("name")


def apply_policy(reference_dir, write=False):
    """Classifica le voci dei cataloghi OGL del manifest e applica A/B/C.

    Dry-run di default: restituisce il riepilogo senza toccare i file. Le
    voci spostate si AGGIUNGONO a pi_local_only/<kind>_local.json: i file
    locali hanno gia' le voci delle policy precedenti, mai sovrascriverli.
    """
    reference_dir = Path(reference_dir)
    manifest_path = reference_dir / "manifest.json"
    manifest = _load(manifest_path)
    moved, sanitized = {}, {}
    for catalog in manifest["catalogs"]:
        rel = catalog.get("file", "")
        if (
            catalog.get("local_only")
            or "pi_local_only" in rel
            or not catalog.get("is_ogc")
        ):
            continue
        kind = catalog["kind"]
        payload = _load(reference_dir / rel)
        entries = payload["entries"] if isinstance(payload, dict) else payload
        kept, out = [], []
        for entry in entries:
            cls = classify(entry)
            if cls in ("A", "B"):
                out.append(entry)
                moved.setdefault(kind, []).append(entry["name"])
                continue
            if cls == "C":
                entry = sanitize_c(entry)
                sanitized.setdefault(kind, []).append(entry["name"])
            kept.append(entry)
        if write and (out or kind in sanitized):
            if isinstance(payload, dict):
                payload["entries"] = kept
            else:
                payload = kept
            _dump(reference_dir / rel, payload)
            catalog["entries"] = len(kept)
            if kind in manifest.get("files", {}):
                manifest["files"][kind]["entries"] = len(kept)
            if out:
                _register_local(manifest, kind, _append_local(reference_dir, kind, out))
    if write and (moved or sanitized):
        _dump(manifest_path, manifest)
    return {"moved": moved, "sanitized": sanitized}


def _append_local(reference_dir, kind, out):
    path = reference_dir / "pi_local_only" / f"{kind}_local.json"
    local = _load(path) if path.exists() else {**LOCAL_HEADER, "entries": []}
    have = {_key(e) for e in local["entries"]}
    local["entries"].extend(e for e in out if _key(e) not in have)
    path.parent.mkdir(parents=True, exist_ok=True)
    _dump(path, local)
    return len(local["entries"])


def _register_local(manifest, kind, count):
    """Conteggio del file locale nel manifest; voce nuova se il file e' nato ora."""
    rel = f"pi_local_only/{kind}_local.json"
    for catalog in manifest["catalogs"]:
        if catalog.get("file") == rel:
            catalog["entries"] = count
            return
    manifest["catalogs"].append(
        {
            "file": rel,
            "kind": f"{kind}_local",
            "license": "OGL-1.0a",
            "is_ogc": False,
            "is_pi": True,
            "local_only": True,
            "entries": count,
            "notes": "Voci PI spostate dal catalogo OGL (scan PI con modello "
            "locale 2026-11-02, tools/apply_pi_scan_policy.py). NON redistribuire.",
        }
    )


def _is_identifier_tag(tag):
    """Tag-etichetta ("race:triaxian", "Darklands"): si toglie, non si riscrive.
    I tag lunghi sono prosa finita nei tag per errore: si sanitizzano."""
    return ":" in tag or len(tag.split()) <= 3


def sanitize_c(entry):
    """Copia della voce C con il testo ripulito. Nome, prerequisiti e campi
    tecnici restano intatti (la sanitize del nome e' vietata)."""
    out = dict(entry)
    for field, value in entry.items():
        if field not in SCANNED_FIELDS or field in ("name", "prerequisites"):
            continue
        if isinstance(value, str):
            if _find_pi(value):
                out[field] = sanitize_text(value, description=True)
        elif isinstance(value, list):
            items = []
            for item in value:
                if not (isinstance(item, str) and _find_pi(item)):
                    items.append(item)
                elif field == "tags" and _is_identifier_tag(item):
                    continue
                else:
                    items.append(sanitize_text(item, description=True))
            out[field] = items
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="applica (default: dry-run)")
    args = ap.parse_args(argv)
    r = apply_policy(REFERENCE_DIR, write=args.write)
    n_moved = sum(len(v) for v in r["moved"].values())
    n_san = sum(len(v) for v in r["sanitized"].values())
    print(
        f"[pi-scan] spostate {n_moved}, sanitizzate {n_san}"
        + ("" if args.write else " (dry-run)")
    )
    for kind in sorted(set(r["moved"]) | set(r["sanitized"])):
        print(
            f"  {kind}: A/B {r['moved'].get(kind, [])}  C {r['sanitized'].get(kind, [])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
