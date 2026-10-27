"""Banco qualita' build — ricalcolo meccanico con src/pc (A2-a2).

Chiude la "lacuna onesta": il Build Agent valida solo plausibilita', qui le
statistiche dichiarate vengono ricalcolate dall'engine deterministico e
confrontate. Il banco RIPORTA, non giudica (D6, piano
planning/2026-10-27-a2a-banco-qualita-build.md): su corpus smoke l'exit e'
sempre 0 — la soglia exit 1 si fissa solo dopo la baseline su fixture LLM.

Uso:
    python tools/bench_build_quality.py                # corpus smoke, report testuale
    python tools/bench_build_quality.py --json out.json
    python tools/bench_build_quality.py --corpus file.jsonl   # fixture LLM future
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.builder import _build_fallback
from src.pc import catalogs
from src.pc.engine import build_character
from src.pc.models import CharacterDraft

# Tempra/Riflessi/Volonta' (dichiarato) -> fort/ref/will (ricalcolato)
SAVES_MAP = {"Tempra": "fort", "Riflessi": "ref", "Volonta": "will"}
# DPR: il pc engine produce attacchi (bonus + dado danno), non danno atteso —
# dichiarato NON verificabile nel report, per tutte le build.
SEED = 42


def classi_complete():
    """Censimento (primo passo a2): classi con hd + progression 1-5 completa."""
    out = []
    for e in catalogs.load("classes"):
        m = e.get("mechanics", {})
        prog = m.get("progression") or []
        if not m.get("hd") or len(prog) < 5:
            continue
        if all(all(k in r for k in ("bab", "fort", "ref", "will")) for r in prog[:5]):
            out.append(e["name"])
    return sorted(out)


def razze_complete():
    """Razze con ability_mods + size + speed (le altre = non_verificabile)."""
    return sorted(
        e["name"]
        for e in catalogs.load("races")
        if all(e.get("mechanics", {}).get(k) for k in ("ability_mods", "size", "speed"))
    )


def corpus_smoke(n=20, seed=SEED):
    """Corpus smoke CI: build fallback (mock) su matrice censita, seed fisso.

    Livelli stratificati (i % 5 + 1) cosi' il livello 1 — regime di
    validazione piu' stretto — e' sempre presente e riportato separato.
    """
    rng = random.Random(seed)
    classi, razze = classi_complete(), razze_complete()
    combo = [(c, r) for c in classi for r in razze]
    rng.shuffle(combo)
    return [
        _build_fallback({"class": c, "race": r, "level": (i % 5) + 1}, [])
        for i, (c, r) in enumerate(combo[:n])
    ]


def confronta(payload):
    """Ricalcola una build e confronta con le statistiche dichiarate.

    Esiti: rifiutato | non_verificabile | concorda | diverge (D6).
    """
    draft_raw = payload.get("pc_draft")
    level = (draft_raw or {}).get("level") or payload.get("request", {}).get("level")
    if not draft_raw:
        return {"esito": "non_verificabile", "motivo": "pc_draft assente", "level": level}
    try:
        draft = CharacterDraft.from_dict(draft_raw)
    except Exception as exc:  # bozza incompatibile = engine rifiuta
        return {"esito": "rifiutato", "motivo": f"draft rifiutato: {exc}", "level": level}
    try:
        sheet = build_character(draft)
    except Exception as exc:  # bozza malformata che l'engine non gestisce
        return {"esito": "rifiutato", "motivo": f"engine: {type(exc).__name__}: {exc}", "level": level}
    if sheet["errors"]:
        return {"esito": "rifiutato", "motivo": "; ".join(sheet["errors"]), "level": level}

    # razza deve essere COMPLETA (ability_mods+size+speed), non solo presente:
    # l'engine accetta le entry incomplete con default e falserebbe il confronto
    if draft.race not in razze_complete():
        return {
            "esito": "non_verificabile",
            "motivo": f"razza senza mechanics complete: {draft.race}",
            "level": level,
            "class": draft.class_,
            "race": draft.race,
        }

    # oggetti fuori catalogo: apply_equipment li ignora con warning — la CA
    # risultante non e' confrontabile (piano: oggetti magici = non_verificabile)
    equip_non_modellato = [w for w in sheet["warnings"] if w.endswith("non in catalogo (valutato a mano)")]

    # bonus razziali ai TS non applicati dall'engine (piano): se un trait
    # della razza concede un bonus diretto ai saving throws, i TS non sono
    # confrontabili — la tolleranza +-1 attribuirebbe alla build un errore
    # dell'engine. "gain...bonus...saving throws" esclude i trait sui DC.
    ts_non_verificabili = any(
        re.search(r"gain[^.]*?bonus[^.]*?saving throws", t.get("text", ""), re.IGNORECASE)
        for t in catalogs.get_race(draft.race)["mechanics"].get("traits", [])
    )

    dich = payload.get("benchmark", {}).get("statistics", {})
    dettaglio = {}
    for label, calc in (("PF", sheet.get("hp")), ("CA", sheet.get("ac"))):
        val = dich.get(label)
        if val is None or calc is None:
            dettaglio[label] = {"esito": "non_verificabile", "dichiarato": val, "ricalcolato": calc}
        elif label == "PF":
            # PF esatto richiede favored_class_bonus noto (D2)
            dettaglio[label] = {
                "esito": "concorda" if calc == val else "diverge",
                "dichiarato": val,
                "ricalcolato": calc,
            }
        else:  # CA +-1, ma NON confrontabile se l'engine ha ignorato oggetti
            dettaglio[label] = (
                {"esito": "non_verificabile", "dichiarato": val, "ricalcolato": calc,
                 "motivo": f"equip non modellato: {'; '.join(equip_non_modellato)}"}
                if equip_non_modellato
                else {
                    "esito": "concorda" if abs(calc - val) <= 1 else "diverge",
                    "dichiarato": val,
                    "ricalcolato": calc,
                }
            )
    ricalc_saves = sheet.get("saves", {})
    for ita, eng in SAVES_MAP.items():
        val = dich.get("saves", {}).get(ita)
        calc = ricalc_saves.get(eng)
        # bonus razziali ai TS non applicati dall'engine => tolleranza +-1 (P2),
        # ma se la razza concede un bonus ai TS dichiarato nel trait, la
        # tolleranza non basta: tutto il gruppo TS e' non_verificabile
        dettaglio[f"TS {ita}"] = (
            {"esito": "non_verificabile", "dichiarato": val, "ricalcolato": calc,
             "motivo": "bonus razziale ai TS non modellato dall'engine"}
            if ts_non_verificabili
            else {"esito": "non_verificabile", "dichiarato": val, "ricalcolato": calc}
            if val is None or calc is None
            else {
                "esito": "concorda" if abs(calc - val) <= 1 else "diverge",
                "dichiarato": val,
                "ricalcolato": calc,
            }
        )
    dettaglio["DPR"] = {"esito": "non_verificabile", "motivo": "engine non calcola danno atteso"}

    verificabili = [d for k, d in dettaglio.items() if k != "DPR"]
    if any(d["esito"] == "non_verificabile" for d in verificabili):
        esito = "non_verificabile"
    elif any(d["esito"] == "diverge" for d in verificabili):
        esito = "diverge"
    else:
        esito = "concorda"
    return {
        "esito": esito,
        "level": draft.level,
        "class": draft.class_,
        "race": draft.race,
        "dettaglio": dettaglio,
    }


def report(risultati):
    """Aggregazione per statistica e livello; livello 1 separato (regime stretto)."""
    stats = ["PF", "CA", "TS Tempra", "TS Riflessi", "TS Volonta", "DPR"]
    esiti = ("concorda", "diverge", "non_verificabile", "rifiutato")

    def bucket(lv):
        return "livello 1" if lv == 1 else "livelli 2-5"

    righe = []
    gruppi = ["senza livello", "livello 1", "livelli 2-5"]
    for grp in gruppi:
        if grp == "senza livello":
            gruppo = [r for r in risultati if not r.get("level")]
        else:
            gruppo = [r for r in risultati if r.get("level") and bucket(r["level"]) == grp]
        if not gruppo:
            continue
        if grp == "senza livello":  # bozze rifiutate/assenti: solo conteggi esito
            esiti_build = {e: sum(1 for r in gruppo if r["esito"] == e) for e in esiti}
            righe.append(f"== senza livello ({len(gruppo)} build: rifiutate o bozza assente) ==")
            righe.append(
                "ESITO BUILD    "
                + " ".join(f"{e}={esiti_build[e]}" for e in ("concorda", "diverge", "non_verificabile", "rifiutato"))
            )
            for r in gruppo:
                righe.append(f"  - {r.get('esito')}: {r.get('motivo', '')[:120]}")
            righe.append("")
            continue
        righe.append(f"== {grp} ({len(gruppo)} build) ==")
        for s in stats:
            conteggi = {e: 0 for e in esiti}
            for r in gruppo:
                d = r.get("dettaglio", {}).get(s)
                if d is None:
                    conteggi[r["esito"]] = conteggi.get(r["esito"], 0) + 1
                else:
                    conteggi[d["esito"]] += 1
            righe.append(
                f"{s:14s} concorda={conteggi['concorda']:3d} diverge={conteggi['diverge']:3d} "
                f"non_verificabile={conteggi['non_verificabile']:3d} rifiutato={conteggi['rifiutato']:3d}"
            )
        esiti_build = {e: sum(1 for r in gruppo if r["esito"] == e) for e in esiti}
        righe.append(
            "ESITO BUILD    "
            + " ".join(f"{e}={esiti_build[e]}" for e in ("concorda", "diverge", "non_verificabile", "rifiutato"))
        )
        righe.append("")
    righe.append("NOTE: tier/meta_tier NON verificato (3 statistiche su 4 misurabili).")
    righe.append("NOTE: DPR non calcolato dall'engine (attacchi = bonus + dado danno).")
    return "\n".join(righe)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="smoke", help="'smoke' o path file .jsonl")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--json", dest="out_json", help="scrivi risultati grezzi JSON")
    args = ap.parse_args(argv)

    if args.corpus == "smoke":
        corpus = corpus_smoke(n=args.n)
    else:
        corpus = [json.loads(l) for l in Path(args.corpus).read_text(encoding="ascii").splitlines() if l.strip()]

    risultati = [confronta(p) for p in corpus]
    print(f"Censimento: classi complete={len(classi_complete())}/40, razze complete={len(razze_complete())}/77")
    print(f"Corpus: {len(risultati)} build (seed fisso {SEED})")
    print()
    print(report(risultati))
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(risultati, indent=1, ensure_ascii=True), encoding="ascii"
        )
    return 0  # D6: riporta, non giudica


if __name__ == "__main__":
    sys.exit(main())
