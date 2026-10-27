#!/usr/bin/env python3
"""Cura una tantum: ripristina le schede di livello schiacciate dal rebuild.

Contesto: il rebuild del corpus ha appiattito a livello 1 le varianti
lvl05/lvl10 (25 famiglie x 2 = 50 file): export.sheet_payload.classi.livelli
e tutte le statistiche sono quelle del livello 1 (censimento 2026-10-26,
misura sonda-noncompetenza pathmaster-dd). La copia pathmaster-dd
(data/reference/builds, snapshot pre-rebuild) conserva i valori corretti.

Cosa fa: per ogni file regressato (livelli TA diversi dai livelli PM con
stesso nome file), sostituisce SOLO export.sheet_payload con la versione PM.
Niente tocca fuori da li': narrative/sheet/composite restano Taverna (i 6
file con PI gunslinger/investigator conservano quindi i loro campi flavor).
_normalized viene fuso (chiavi PM aggiunte, chiavi TA preservate).

Eccezione wizard: il snapshot PM e' pre-cura (tools/cura_armatura_stub_wizard.py)
e contiene ancora "Armatura leggera" inventata: per le 2 varianti lvl05/10
della famiglia la voce viene rimossa dopo il ripristino e la cura resta
dichiarata in _normalized.curaArmaturaStub (messo da questa stessa cura).

Verifica: nome/classi/razza/query_params invariati rispetto al file TA;
dopo la scrittura il file reloadato ha livelli == PM. Fallisce senza scrivere
il file in caso di mismatch.

Uso: .venv/Scripts/python tools/restore_schede_livello.py [--dry-run]
Richiede: pathmaster-dd raggiungibile a ../../pathmaster-dd/data/reference/builds
(override con env PATHMASTER_BUILDS_DIR).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TA_BUILDS = ROOT / "src/data/builds"
PM_BUILDS = Path(
    os.environ.get("PATHMASTER_BUILDS_DIR")
    or ROOT.parent / "pathmaster-dd/data/reference/builds"
)
VOCE = "Armatura leggera"
FAMIGLIA_WIZARD = "wizard_elf_universalist"


def _livelli(doc) -> list:
    return [
        c.get("livelli")
        for c in doc.get("export", {}).get("sheet_payload", {}).get("classi", [])
    ]


def _identita(doc) -> dict:
    sp = doc.get("export", {}).get("sheet_payload", {})
    return {
        "nome": doc.get("nome") or doc.get("export", {}).get("nome"),
        "classi": [(c.get("nome"), c.get("archetipi")) for c in sp.get("classi", [])],
        "razza": sp.get("razza"),
        "query_params": doc.get("query_params") or {},
    }


def _rimuovi_voce(node, rimossi: list, rel: str, path: str = "") -> None:
    if isinstance(node, dict):
        for k in list(node.keys()):
            v = node[k]
            p = f"{path}.{k}" if path else k
            if (
                isinstance(v, list)
                and k in ("equipaggiamento", "inventario")
                and VOCE in v
            ):
                node[k] = [x for x in v if x != VOCE]
                rimossi.append(f"{rel}: {p}")
            else:
                _rimuovi_voce(v, rimossi, rel, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _rimuovi_voce(v, rimossi, rel, f"{path}[{i}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PM_BUILDS.is_dir():
        sys.exit(f"corpus pathmaster non trovato: {PM_BUILDS}")

    errori: list[str] = []
    scritti = 0
    visti = 0

    for pm_path in sorted(PM_BUILDS.rglob("*.json")):
        rel = pm_path.relative_to(PM_BUILDS)
        if rel.name.startswith("_") or "_lvl" not in rel.name:
            continue
        ta_path = TA_BUILDS / rel
        if not ta_path.exists():
            continue
        visti += 1
        ta = json.loads(ta_path.read_text(encoding="utf-8"))
        pm = json.loads(pm_path.read_text(encoding="utf-8"))
        if _livelli(ta) == _livelli(pm):
            continue

        rel_s = rel.as_posix()
        # guardia identita': stessa build, stessa famiglia
        for campo, val_ta in _identita(ta).items():
            if val_ta != _identita(pm)[campo]:
                errori.append(f"{rel_s}: identita diversa ({campo})")
                break
        if errori and errori[-1].startswith(rel_s):
            continue

        sheet = json.loads(json.dumps(pm["export"]["sheet_payload"]))  # copia profonda
        rimossi: list[str] = []
        if rel.stem.startswith(FAMIGLIA_WIZARD):
            _rimuovi_voce(sheet, rimossi, rel_s)

        export = dict(ta.get("export") or {})
        export["sheet_payload"] = sheet
        ta["export"] = export
        norm = dict(pm.get("_normalized") or {})
        norm.update(ta.get("_normalized") or {})  # TA vince (es. curaArmaturaStub)
        if rimossi:
            cura = dict(norm.get("curaArmaturaStub") or {})
            cura["voce_rimossa"] = VOCE
            cura["restoreSchedeLivello"] = (
                "sheet ripristinata dal snapshot pathmaster pre-rebuild; voce "
                "inventata dal fallback stub rimossa dopo il ripristino"
            )
            cura["da"] = sorted(set(cura.get("da") or []) | set(rimossi))
            norm["curaArmaturaStub"] = cura
        if norm:
            ta["_normalized"] = norm

        if _livelli(ta) != _livelli(pm):
            errori.append(f"{rel_s}: livelli dopo restore != PM")
            continue

        if not args.dry_run:
            ta_path.write_text(
                json.dumps(ta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        scritti += 1
        print(
            f"{'[dry] ' if args.dry_run else ''}ripristinato {rel_s}: livelli {_livelli(ta)}"
        )

    if errori:
        print("\nERRORI:", file=sys.stderr)
        for e in errori:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(
        f"\n{'[dry-run] ' if args.dry_run else ''}{scritti} file ripristinati "
        f"(candidati lvl: {visti}), 0 errori"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
