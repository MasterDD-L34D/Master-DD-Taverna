#!/usr/bin/env python3
"""Gate oracolo (raccomandazione A del censimento 2026-10-26).

Chiude il loop generazione<->oracolo: la sonda-noncompetenza di pathmaster-dd
(l'oracolo deterministico PF1e) corre sul corpus build di QUESTA repo e il
gate fallisce se i conteggi superano le soglie in data/oracolo-gate.json.
In questo modo una build nuova o modificata che introduce equipaggiamento
non competente o unknown NON entra nel corpus in silenzio.

Perche' non in CI: la sonda vive nel repo privato pathmaster-dd; la CI
pubblica di Taverna non ci accede. Il gate e' parte del rituale locale
(verify_master_dd.py -> launch.py test). Il checkout pathmaster deve avere
la patch SONDA_OUT (pathmaster PR #253) o la sonda riscrivera il JSON
tracciato di quel repo.

Uso:
  .venv/Scripts/python tools/gate_oracolo.py           # verde/rosso
  .venv/Scripts/python tools/gate_oracolo.py --update  # riscrive le soglie
                                                       # = fotografia attuale
                                                       # (solo dopo fix ratificati)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TA_BUILDS = ROOT / "src/data/builds"
GATE = ROOT / "data/oracolo-gate.json"
LAST = ROOT / "data/oracolo-gate-last.json"
PATHMASTER = Path(os.environ.get("PATHMASTER_REPO") or ROOT.parent / "pathmaster-dd")
SONDA = PATHMASTER / "tools/sonda-noncompetenza.mts"

CHIAVI = [("max_ko_armi", "koArmi"), ("max_ko_armature", "koArmature"), ("max_unknown", "unknown")]


def osserva(risultati: dict) -> dict:
    """Conteggi per build (non per voce), come la stampa a console della sonda."""
    return {
        "koArmi": sum(1 for r in risultati.values() if r.get("koArmi", 0) > 0),
        "koArmature": sum(1 for r in risultati.values() if r.get("koArmature", 0) > 0),
        "unknown": sum(1 for r in risultati.values() if r.get("unknown", 0) > 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true", help="riscrive le soglie = fotografia attuale")
    args = ap.parse_args()

    if not Sonda_disponibile():
        print(f"SALTATO: sonda non trovata in {SONDA} (PATHMASTER_REPO={PATHMASTER})")
        return 0

    soglie = json.loads(GATE.read_text(encoding="utf-8"))

    env = {
        **os.environ,
        "MASTER_DD_BUILDS_DIR": str(TA_BUILDS),
        "SONDA_OUT": str(LAST),
    }
    # shell=True: su Windows npx e' un .cmd e CreateProcess non risolve
    # l'estensione; il comando e' fisso e trusted, niente input esterno.
    res = subprocess.run(
        "npx tsx tools/sonda-noncompetenza.mts",
        cwd=PATHMASTER, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=True,
    )
    if res.returncode != 0 or not LAST.exists():
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        sys.exit(f"ERRORE: sonda fallita (exit {res.returncode})")

    oss = osserva(json.loads(LAST.read_text(encoding="utf-8")))

    if args.update:
        for chiave_soglia, chiave_oss in CHIAVI:
            soglie[chiave_soglia] = oss[chiave_oss]
        GATE.write_text(json.dumps(soglie, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"OK: soglie aggiornate = fotografia attuale {oss}")
        return 0

    fuori = []
    for chiave_soglia, chiave_oss in CHIAVI:
        if oss[chiave_oss] > soglie[chiave_soglia]:
            fuori.append(f"{chiave_oss}: osservato {oss[chiave_oss]} > soglia {soglie[chiave_soglia]}")
    if fuori:
        print("GATE ORACOLO ROSSO:", file=sys.stderr)
        for f in fuori:
            print(f"  - {f}", file=sys.stderr)
        print("  Dettaglio nel JSON dell'ultima corsa: data/oracolo-gate-last.json", file=sys.stderr)
        print("  Se la deviazione e' un fix legittimo: abbassa le soglie con --update (commit motivato).", file=sys.stderr)
        return 1
    print(f"OK: gate oracolo verde {oss} (soglie {soglie['max_ko_armi']}/"
          f"{soglie['max_ko_armature']}/{soglie['max_unknown']})")
    return 0


def Sonda_disponibile() -> bool:
    return SONDA.exists()


if __name__ == "__main__":
    raise SystemExit(main())
