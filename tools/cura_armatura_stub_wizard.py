#!/usr/bin/env python3
"""Cura una tantum: armatura inventata nelle build wizard del corpus Taverna.

Contesto: il fallback dello stub builder (PR #545) inseriva "Armatura leggera"
anche per classi non competenti. Le 6 build `wizard_elf_universalist*` (3 live
in src/data/builds + 3 snapshot in src/data/builds/archive) conservano la voce
in inventario (live) o equipaggiamento+inventario+sheet_markdown (archive).
La fusione d'archivio del sync pathmaster-dd fa UNIONE su equip/inventario:
lasciare l'archivio sporco reintrodurrebbe la voce nel corpus a valle.

Cosa fa: rimuove la voce "Armatura leggera" dalle liste equipaggiamento /
inventario (in tutte le copie annidate) e la riga "- Armatura leggera" dai
campi markdown, SOLO nei 6 file della famiglia universalist, e dichiara la
cura in `_normalized.curaArmaturaStub`. La famiglia evoker e' pulita (lo
verifica e fallisce se non lo e').

Verifica di derivazione (non e' una patch a mano): dopo la cura, le liste
equipaggiamento/inventario di export.sheet_payload devono combaciare con
l'output ATTUALE di build_stub_payload chiamato con i query_params del file
stesso. Se non combaciano, lo script fallisce e non scrive.

Uso: .venv/Scripts/python tools/cura_armatura_stub_wizard.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.builder.stub_builder import build_stub_payload

VOCE = "Armatura leggera"
RIGA_MD = "- Armatura leggera"
FAMIGLIA_SPORCA = "wizard_elf_universalist"
FAMIGLIA_PULITA = "wizard_human_evoker"
SUFFISSI = ("", "_lvl05", "_lvl10")
CARTELLE = (ROOT / "src/data/builds", ROOT / "src/data/builds/archive")

rimossi: list[str] = []


def _cura(node, path, rel):
    """Rimuove la voce dalle liste equip/inventario e la riga dai markdown."""
    if isinstance(node, dict):
        for k in list(node.keys()):
            v = node[k]
            p = f"{path}.{k}" if path else k
            if isinstance(v, list) and k in ("equipaggiamento", "inventario") and VOCE in v:
                node[k] = [x for x in v if x != VOCE]
                rimossi.append(f"{rel}: {p}")
            elif isinstance(v, str) and RIGA_MD in v:
                node[k] = v.replace(f"{RIGA_MD}\n", "").replace(RIGA_MD, "")
                rimossi.append(f"{rel}: {p} (markdown)")
            else:
                _cura(v, p, rel)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _cura(v, f"{path}[{i}]", rel)


def _contiene_voce(node):
    if isinstance(node, str):
        return VOCE in node
    if isinstance(node, list):
        return any(_contiene_voce(v) for v in node)
    if isinstance(node, dict):
        return any(_contiene_voce(v) for v in node.values())
    return False


def _verifica_vs_stub(doc, rel):
    """Le liste curate devono coincidere con lo stub attuale (stessi params)."""
    qp = doc.get("query_params") or {}
    payload = build_stub_payload(
        class_name=qp.get("class"),
        race=qp.get("race"),
        archetype=qp.get("archetype"),
        level=qp.get("level"),
        mode=qp.get("mode"),
        body=doc.get("body_params") or None,
    )
    sheet_stub = (payload.get("export") or {}).get("sheet_payload") or payload.get("sheet") or {}
    sheet_file = (doc.get("export") or {}).get("sheet_payload") or {}
    errori = []
    for campo in ("equipaggiamento", "inventario"):
        if sheet_file.get(campo) != sheet_stub.get(campo):
            errori.append(
                f"{rel}: {campo} diverso dallo stub attuale "
                f"(file={sheet_file.get(campo)} stub={sheet_stub.get(campo)})"
            )
    return errori


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    errori = []
    scritti = 0
    for cartella in CARTELLE:
        for stem, atteso_sporco in ((FAMIGLIA_SPORCA, True), (FAMIGLIA_PULITA, False)):
            for suf in SUFFISSI:
                path = cartella / f"{stem}{suf}.json"
                rel = path.relative_to(ROOT).as_posix()
                doc = json.loads(path.read_text(encoding="utf-8"))
                sporco = _contiene_voce(doc)
                if atteso_sporco and not sporco:
                    errori.append(f"{rel}: attesa la voce '{VOCE}', assente")
                    continue
                if not atteso_sporco and sporco:
                    errori.append(f"{rel}: famiglia evoker attesa pulita, voce presente")
                    continue
                if not sporco:
                    continue
                rimossi.clear()
                _cura(doc, "", rel)
                if _contiene_voce(doc):
                    errori.append(f"{rel}: voce residua dopo la cura")
                    continue
                errori.extend(_verifica_vs_stub(doc, rel))
                if errori:
                    continue
                cura = {
                    "voce_rimossa": VOCE,
                    "da": sorted(rimossi),
                    "motivo": "fallback stub inventava armatura per classe non competente (PR #545)",
                    "verifica": "liste equip/inventario identiche all'output attuale di build_stub_payload",
                }
                doc["_normalized"] = {**(doc.get("_normalized") or {}), "curaArmaturaStub": cura}
                if not args.dry_run:
                    path.write_text(
                        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                scritti += 1
                print(f"{'[dry] ' if args.dry_run else ''}curato {rel}: {len(rimossi)} punti")

    if errori:
        print("\nERRORI:", file=sys.stderr)
        for e in errori:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"\n{'[dry-run] ' if args.dry_run else ''}{scritti} file curati, 0 errori")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
