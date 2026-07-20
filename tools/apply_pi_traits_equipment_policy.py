#!/usr/bin/env python3
"""Applica la policy PI a traits.json ed equipment_mundane.json (Task 3 esteso).

Estende ai cataloghi traits/equipment la disciplina gia' applicata ai feats
(tools/apply_pi_feats_policy.py, reports/pi_feats_apply.md), su decisione del
controller 2026-07-19 dopo l'estensione del gate (tools/legal_filter.py):

  A — PI nel NOME (incl. la forma aggettivale "Arodenite": \\bAroden\\b non
      matcha il nome, ma l'identita' e' PI per decisione controller) ->
      spostamento verbatim in pi_local_only (sanitize del nome vietata).
  B — prereq vincolante PI ("Ostenso" nei prerequisites) -> pi_local_only.
  C — PI solo in description -> sanitize in place con le regole
      description-only di tools/sanitize_reference_pi.py (aggiunte "Aroden"
      e "Sothis" per questa policy).

Fail-closed come il tool feats: conteggi attesi hardcoded, mappa delle
violazioni del gate verificata ESATTA prima di toccare i dati, check
riferimenti pendenti (dangling refs) a vuoto, guardie post-applicazione
(gate 0 sui due cataloghi, conteggi, nomi intatti). Default DRY-RUN:
--write applica e scrive cataloghi, local, manifest e report.

Nota "Reassuring Advice": le 3 occorrenze del gate sono 3 citazioni di
"Aroden" nella STESSA description (1 sola entry, nessun duplicato nel
catalogo): la dedup non e' applicabile.

Uso:
  python tools/apply_pi_traits_equipment_policy.py          # dry-run
  python tools/apply_pi_traits_equipment_policy.py --write  # applica
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.legal_filter import SCANNED_FIELDS, _find_pi
from tools.sanitize_reference_pi import sanitize_text

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
TRAITS_JSON = REFERENCE_DIR / "ogl" / "traits.json"
EQUIPMENT_JSON = REFERENCE_DIR / "ogl" / "equipment_mundane.json"
MANIFEST_JSON = REFERENCE_DIR / "manifest.json"
LOCAL_DIR = REFERENCE_DIR / "pi_local_only"
TRAITS_LOCAL = LOCAL_DIR / "traits_local.json"
EQUIPMENT_LOCAL = LOCAL_DIR / "equipment_local.json"
REPORT_PATH = REPO_ROOT / "reports" / "pi_traits_equipment_apply.md"

POLICY_DATE = "2026-07-19"

# Conteggi attesi pre-policy (fail-closed: stati diversi = stato non
# pre-policy o doppia applicazione).
EXPECTED_TRAITS = 470
EXPECTED_EQUIPMENT = 790

# Classificazione (gate Task 3 + decisione controller; motivo per entry nel
# report). A = PI nel nome, B = prereq vincolante PI, C = solo description.
TRAITS_A = {"Aldori Caution", "Arodenite Sword Training", "Arodenite Historian"}
TRAITS_B = {"Gifted Smuggler"}
TRAITS_C = {
    "Dueling Cloak Adept", "Crusader", "Divine Denier", "Bureaucrat's Favored",
    "Scholar of the Analects", "Stabbing Spells", "Reassuring Advice",
}
EQUIPMENT_A = {
    "Hellknight leather", "Hellknight half-plate", "Hellknight plate",
    "Alkenstar fortress plate",
}

# Mappa attesa delle violazioni del gate (entry -> campi con hit), derivata
# dal report di Task 3: verificata ESATTA prima dell'applicazione.
# Fix quality review: "Osiria" (variante di Osirion) e' entrata nel gate;
# sullo stato pre-policy il prereq di Bureaucrat's Favored ha quindi un hit
# in "prerequisites" (sanitizzato con i replacement del set base, disciplina
# prereq dei feats: NON i description-only).
EXPECTED_HITS = {
    "traits": {
        "Aldori Caution": {"name", "description"},
        "Dueling Cloak Adept": {"description"},
        "Arodenite Sword Training": {"description"},
        "Scholar of the Analects": {"description"},
        "Stabbing Spells": {"description"},
        "Arodenite Historian": {"description"},
        "Reassuring Advice": {"description"},
        "Crusader": {"description"},
        "Divine Denier": {"description"},
        "Bureaucrat's Favored": {"description", "prerequisites"},
        "Gifted Smuggler": {"prerequisites"},
    },
    "equipment": {
        "Hellknight leather": {"name", "description"},
        "Hellknight half-plate": {"name", "description"},
        "Hellknight plate": {"name", "description"},
        "Alkenstar fortress plate": {"name", "description"},
    },
}

TRAITS_LOCAL_NOTE = (
    "Tratti con Product Identity nel nome o nei prerequisiti (categorie "
    "A/B), spostati dal catalogo OGL con la policy 2026-07-19 "
    "(reports/pi_traits_equipment_apply.md). NON redistribuire. Generato da "
    "tools/apply_pi_traits_equipment_policy.py; indicizza con "
    "tools/index_rag.py --include-local.")
EQUIPMENT_LOCAL_NOTE = (
    "Equipment mundano con Product Identity nel nome (categoria A), "
    "spostato dal catalogo OGL con la policy 2026-07-19 "
    "(reports/pi_traits_equipment_apply.md). NON redistribuire. Generato da "
    "tools/apply_pi_traits_equipment_policy.py; indicizza con "
    "tools/index_rag.py --include-local.")

TRAITS_LOCAL_HEADER = {
    "_license": "OGL-1.0a",
    "_source": "Archives of Nethys (aonprd.com) — traits PI spostati dal "
               "catalogo OGL (policy 2026-07-19, Task 3 esteso); local only, "
               "not redistributed",
}
EQUIPMENT_LOCAL_HEADER = {
    "_license": "OGL-1.0a",
    "_source": "Archives of Nethys (aonprd.com) — equipment PI spostato dal "
               "catalogo OGL (policy 2026-07-19, Task 3 esteso); local only, "
               "not redistributed",
}


def _fail(msg):
    print(f"[apply-pi-te] ERRORE: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_hits(entries):
    """Mappa entry -> set di campi scansionati con hit del gate esteso."""
    hits = {}
    for entry in entries:
        for field, value in entry.items():
            if field not in SCANNED_FIELDS:
                continue
            texts = value if isinstance(value, list) else [value]
            for text in texts:
                if isinstance(text, str) and _find_pi(text):
                    hits.setdefault(entry.get("name", "?"), set()).add(field)
    return hits


def _check_dangling(all_catalog_entries, moved_names):
    """Riferimenti esatti (prerequisites/references) alle entry spostate:
    devono essere zero, altrimenti lo spostamento lascia ref pendenti."""
    dangling = []
    for catalog, entries in all_catalog_entries:
        for entry in entries:
            other = entry.get("name") or ""
            if other in moved_names:
                continue
            for field in ("prerequisites", "references"):
                items = entry.get(field) or []
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    if str(item).strip().lower() in {n.lower() for n in moved_names}:
                        dangling.append((catalog, other, field, item))
    return dangling


def apply_policy(write=False):
    traits_payload = _load(TRAITS_JSON)
    equipment_payload = _load(EQUIPMENT_JSON)
    traits = traits_payload["entries"]
    equipment = equipment_payload["entries"]

    # --- Guardie pre-applicazione (fail-closed) ---------------------------
    if len(traits) != EXPECTED_TRAITS:
        _fail(f"entry in traits.json: {len(traits)} != {EXPECTED_TRAITS} "
              "(stato non pre-policy? doppia applicazione?)")
    if len(equipment) != EXPECTED_EQUIPMENT:
        _fail(f"entry in equipment_mundane.json: {len(equipment)} != "
              f"{EXPECTED_EQUIPMENT} (stato non pre-policy?)")

    hits_t = _gate_hits(traits)
    hits_e = _gate_hits(equipment)
    if hits_t != EXPECTED_HITS["traits"]:
        _fail(f"mappa violazioni traits inattesa: {hits_t} != "
              f"{EXPECTED_HITS['traits']} (catalogo cambiato? riclassificare)")
    if hits_e != EXPECTED_HITS["equipment"]:
        _fail(f"mappa violazioni equipment inattesa: {hits_e} != "
              f"{EXPECTED_HITS['equipment']} (catalogo cambiato? riclassificare)")

    names_t = [e["name"] for e in traits]
    names_e = [e["name"] for e in equipment]
    for name in sorted(TRAITS_A | TRAITS_B | TRAITS_C):
        if names_t.count(name) != 1:
            _fail(f"entry traits attesa una sola volta: {name} "
                  f"(trovate {names_t.count(name)})")
    for name in sorted(EQUIPMENT_A):
        if names_e.count(name) != 1:
            _fail(f"entry equipment attesa una sola volta: {name} "
                  f"(trovate {names_e.count(name)})")

    # Le C devono avere hit SOLO in description (regola stretta); eccezione
    # documentata: il prereq "Osiria" di Bureaucrat's Favored (fix quality
    # review), sanitizzato con i replacement del set base.
    for name, fields in hits_t.items():
        if name in TRAITS_C and fields != {"description"}:
            if not (name == "Bureaucrat's Favored"
                    and fields == {"description", "prerequisites"}):
                _fail(f"entry C con hit fuori description: {name} {sorted(fields)}")

    moved_t = TRAITS_A | TRAITS_B
    moved_e = EQUIPMENT_A
    # Dangling refs su tutti i cataloghi OGL committati.
    all_catalogs = [("traits", traits), ("equipment", equipment)]
    for extra in ("feats.json", "spells.json", "items.json", "classes.json",
                  "races.json", "archetypes.json", "abilities.json", "skills.json"):
        payload = _load(REFERENCE_DIR / "ogl" / extra)
        all_catalogs.append((extra.replace(".json", ""),
                             payload.get("entries", [])))
    dangling = _check_dangling(all_catalogs, moved_t | moved_e)
    if dangling:
        _fail(f"riferimenti pendenti verso le entry spostate: {dangling}")

    # --- Applicazione ------------------------------------------------------
    moved_traits = [e for e in traits if e["name"] in moved_t]
    moved_equipment = [e for e in equipment if e["name"] in moved_e]
    kept_traits = [e for e in traits if e["name"] not in moved_t]
    kept_equipment = [e for e in equipment if e["name"] not in moved_e]

    sanitized = []
    for e in kept_traits:
        if e["name"] in TRAITS_C:
            before = e["description"]
            after = sanitize_text(before, description=True)
            if after == before:
                _fail(f"sanitize C senza effetto: {e['name']}")
            e["description"] = after
            # Prereq con citazione PI (disciplina feats: replacement del set
            # BASE, mai i description-only): "Osiria" in Bureaucrat's Favored.
            if isinstance(e.get("prerequisites"), list):
                e["prerequisites"] = [sanitize_text(x) for x in e["prerequisites"]]
            sanitized.append(e["name"])
    if sorted(sanitized) != sorted(TRAITS_C):
        _fail(f"sanitize C parziale: {sorted(sanitized)} != {sorted(TRAITS_C)}")

    # --- Guardie post-applicazione -----------------------------------------
    if _gate_hits(kept_traits) or _gate_hits(kept_equipment):
        _fail(f"residui del gate dopo l'applicazione: "
              f"{_gate_hits(kept_traits)}, {_gate_hits(kept_equipment)}")
    traits_after = len(kept_traits)
    equipment_after = len(kept_equipment)
    if (traits_after, equipment_after) != (EXPECTED_TRAITS - 4, EXPECTED_EQUIPMENT - 4):
        _fail(f"conteggi post inattesi: traits={traits_after}, "
              f"equipment={equipment_after}")

    summary = {
        "moved_traits": sorted(moved_t),
        "moved_equipment": sorted(moved_e),
        "sanitized": sorted(sanitized),
        "traits_after": traits_after,
        "equipment_after": equipment_after,
    }

    if write:
        traits_payload["entries"] = kept_traits
        equipment_payload["entries"] = kept_equipment
        TRAITS_JSON.write_text(
            json.dumps(traits_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        EQUIPMENT_JSON.write_text(
            json.dumps(equipment_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        TRAITS_LOCAL.write_text(
            json.dumps({**TRAITS_LOCAL_HEADER, "entries": moved_traits},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        EQUIPMENT_LOCAL.write_text(
            json.dumps({**EQUIPMENT_LOCAL_HEADER, "entries": moved_equipment},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        _update_manifest(summary)
        REPORT_PATH.write_text(_render_report(), encoding="utf-8")
        print(f"[apply-pi-te] scritti: traits.json ({traits_after}), "
              f"equipment_mundane.json ({equipment_after}), traits_local.json (4), "
              f"equipment_local.json (4), manifest, {REPORT_PATH.name}")
    return summary


def _update_manifest(summary):
    manifest = _load(MANIFEST_JSON)
    for catalog in manifest["catalogs"]:
        if catalog.get("file") == "ogl/traits.json":
            catalog["entries"] = summary["traits_after"]
            catalog["notes"] = (
                "Tratti Basic (Combat/Faith/Magic/Social) + Equipment; "
                "categorie PI escluse by design; 80 entry PI rimosse "
                "(reports/pi_removed_traits.txt). Policy PI 2026-07-19 "
                "(Task 3 esteso): 4 entry PI-identity spostate in "
                "pi_local_only/traits_local.json, 7 description sanitize "
                "(reports/pi_traits_equipment_apply.md).")
            catalog["last_verified"] = POLICY_DATE
        elif catalog.get("file") == "ogl/equipment_mundane.json":
            catalog["entries"] = summary["equipment_after"]
            catalog["notes"] = (
                "Armi/armature/gear mundane con costi/pesi/danni strutturati; "
                "source per-voce dalle pagine dettaglio. Policy PI 2026-07-19 "
                "(Task 3 esteso): 4 entry PI-identity spostate in "
                "pi_local_only/equipment_local.json "
                "(reports/pi_traits_equipment_apply.md).")
            catalog["last_verified"] = POLICY_DATE
    local_specs = [
        ("pi_local_only/traits_local.json", "traits_local",
         "Archives of Nethys (aonprd.com)", TRAITS_LOCAL_NOTE),
        ("pi_local_only/equipment_local.json", "equipment_local",
         "Archives of Nethys (aonprd.com)", EQUIPMENT_LOCAL_NOTE),
    ]
    for path, kind, source, note in local_specs:
        existing = [c for c in manifest["catalogs"] if c.get("file") == path]
        if not existing:
            manifest["catalogs"].append({
                "file": path,
                "kind": kind,
                "source": source,
                "license": "OGL-1.0a",
                "is_ogc": False,
                "is_pi": False,
                "cup_allowed": False,
                "local_only": True,
                "entries": 4,
                "notes": note,
                "last_verified": POLICY_DATE,
            })
        else:
            # Riallineamento anti-drift (come per feats_local).
            existing[0]["entries"] = 4
            existing[0]["notes"] = note
            existing[0]["last_verified"] = POLICY_DATE
    manifest["files"]["traits"]["entries"] = summary["traits_after"]
    manifest["files"]["equipment"]["entries"] = summary["equipment_after"]
    # Il manifest committato termina con newline (convenzione repo).
    MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


# Motivo per entry (tabella del report; classificazione documentata).
MOTIVI = {
    "Aldori Caution": ("A", "traits_local", "\"Aldori\" nel nome (organizzazione PI)"),
    "Arodenite Sword Training": ("A", "traits_local",
        "\"Arodenite\" nel nome (aggettivo della deita' PI; \\bAroden\\b non "
        "matcha il nome, identita' PI per decisione controller)"),
    "Arodenite Historian": ("A", "traits_local",
        "\"Arodenite\" nel nome (come sopra)"),
    "Gifted Smuggler": ("B", "traits_local",
        "prerequisito vincolante PI: \"Ostenso\""),
    "Dueling Cloak Adept": ("C", "sanitize in place",
        "\"an Aldori dueling sword\" in description -> \"a dueling sword\""),
    "Crusader": ("C", "sanitize in place",
        "\"the Worldwound\" in description -> \"a demon-blighted land\""),
    "Divine Denier": ("C", "sanitize in place",
        "\"Rahadoumi\" in description -> \"godless\""),
    "Bureaucrat's Favored": ("C", "sanitize in place",
        "\"Sothis\" in description -> \"a desert metropolis\" (regola nuova); "
        "prereq \"Osiria\" -> \"an ancient desert kingdom\" (set base; fix "
        "quality review: requisito di associazione a una corte, il toponimo "
        "neutralizzato lascia il requisito coerente — a differenza di "
        "\"Ostenso\" in Gifted Smuggler, unico contenuto del prereq -> B)"),
    "Scholar of the Analects": ("C", "sanitize in place",
        "\"Aroden\" in description -> \"a dead god\" (regola nuova)"),
    "Stabbing Spells": ("C", "sanitize in place",
        "\"Aroden\" in description -> \"a dead god\" (regola nuova)"),
    "Reassuring Advice": ("C", "sanitize in place",
        "\"Aroden\" x3 nella stessa description -> \"a dead god\"; NOTA: 1 "
        "sola entry (le 3 occorrenze del gate sono nella stessa description), "
        "dedup non applicabile"),
    "Hellknight leather": ("A", "equipment_local", "\"Hellknight\" nel nome"),
    "Hellknight half-plate": ("A", "equipment_local", "\"Hellknight\" nel nome"),
    "Hellknight plate": ("A", "equipment_local", "\"Hellknight\" nel nome"),
    "Alkenstar fortress plate": ("A", "equipment_local", "\"Alkenstar\" nel nome"),
}


def _render_report():
    out = []
    add = out.append
    add("# Applicazione policy PI traits + equipment — " + POLICY_DATE)
    add("")
    add("> Generato da `tools/apply_pi_traits_equipment_policy.py --write`. "
        "Estensione della policy PI (decisione controller 2026-07-19) ai "
        "debiti preesistenti rilevati dal gate esteso di Task 3 "
        "(`tools/legal_filter.py`): stessa disciplina di "
        "`reports/pi_feats_apply.md` (A/B -> `pi_local_only`, C -> sanitize "
        "description, fail-closed sui conteggi).")
    add("")
    add("## Tabella entry -> destinazione")
    add("")
    add("| Entry | Catalogo | Cat. | Destinazione | Motivo |")
    add("| --- | --- | --- | --- | --- |")
    for name in sorted(MOTIVI, key=str.lower):
        cat, dest, motivo = MOTIVI[name]
        catalogo = "equipment" if dest == "equipment_local" else "traits"
        add(f"| {name} | {catalogo} | {cat} | {dest} | {motivo} |")
    add("")
    add("## Conteggi")
    add("")
    add("- `traits.json`: 470 -> **466** (A=3 + B=1 in `pi_local_only/traits_local.json`; "
        "C=7 description sanitize in place).")
    add("- `equipment_mundane.json`: 790 -> **786** (A=4 in "
        "`pi_local_only/equipment_local.json`).")
    add("- Nessun riferimento pendente (check dangling refs su tutti i "
        "cataloghi OGL: prerequisites/references).")
    add("- Gate post-applicazione: **0 violazioni** su traits ed equipment "
        "(scansione `legal_filter._find_pi`, campi scansionati).")
    add("")
    add("## Follow-up (fuori scope, documentati)")
    add("")
    add("- **Titoli libro PI nei campi `source`** (il gate non scansiona "
        "`source`; le 8 feats sanitize in Task 3 erano in `tags`, che e' "
        "scansionato): equipment \"Pirates of the Inner Sea\" x10, \"Inner "
        "Sea Intrigue/Temples/World Guide\" x13, \"Path of the Hellknight\" "
        "(Manacles (mithral)); traits \"Knights of the Inner Sea\" x9, "
        "\"Path of the Hellknight\" (Godclaw Disciple). Decisione separata.")
    add("- `reports/pi_feats_triage.md` resta la fotografia storica di "
        "feats.json@364cd15: non rigenerato per decisione del controller.")
    add("")
    add("## Fix quality review 2026-07-19 (pre-commit)")
    add("")
    add("- **\"Osiria\"** nei prerequisites di `Bureaucrat's Favored` "
        "(\"court of the Black Dome in Osiria\"): variante di \"Osirion\" "
        "non coperta dalla lista. Aggiunta ai candidati del gate "
        "(`GATE_CANDIDATE_TERMS`) e sanitizzata con la forma neutra della "
        "famiglia Osirion (\"an ancient desert kingdom\", set base). "
        "Classificazione confermata C: requisito di associazione a una "
        "corte (non etnia/deita' vincolante); il toponimo neutralizzato "
        "lascia il requisito coerente.")
    add("- **Ritocco grammaticale post-replacement** (2 description, "
        "intervento manuale): `Stabbing Spells` \"a dead god wrote "
        "much...\" -> \"A dead god wrote much...\" (maiuscola a inizio "
        "frase); `Divine Denier` \"you're a godless objecting\" -> "
        "\"you're a godless one objecting\".")
    add("")
    return "\n".join(out) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="applica e scrive cataloghi, local, manifest e report")
    args = parser.parse_args()
    summary = apply_policy(write=args.write)
    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"[apply-pi-te] {mode} OK: traits {EXPECTED_TRAITS}->{summary['traits_after']}, "
          f"equipment {EXPECTED_EQUIPMENT}->{summary['equipment_after']}, "
          f"local traits={len(summary['moved_traits'])} equipment={len(summary['moved_equipment'])}, "
          f"sanitize C={len(summary['sanitized'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
