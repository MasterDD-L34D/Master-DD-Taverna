#!/usr/bin/env python3
"""Triage delle entry PI preesistenti in data/reference/ogl/feats.json.

Implementa il Task 1 del piano planning/2026-07-19-pi-feats-triage.md:
scansione word-boundary con la lista estesa (`PI_TERMS`, 75 termini),
categorizzazione
A/B/C/D, check dei riferimenti pendenti (dangling refs) e generazione del
report reports/pi_feats_triage.md (evidenza della decisione policy).

Categorie (in conflitto vince la piu' severa: D > A > B > C):
  A — match PI nel NOME: identita' PI, spostamento in pi_local_only
      (la sanitize del nome e' vietata).
  B — match di una DEITA' nei prerequisites: prerequisito deita-specifico,
      spostamento in pi_local_only.
  C — match solo in description (o PI non-deita' nei prerequisites):
      sanitize in place (tool word-boundary, Task 2).
  D — artifact della sanitize storica naive (nomi corrotti, residui
      ISM/ISWG, pattern "a frontier landn"): ripristino da fonte, poi
      ricategorizzazione.

Uso:
  python tools/triage_pi_feats.py            # report markdown su stdout
  python tools/triage_pi_feats.py --write    # scrive reports/pi_feats_triage.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sanitize_reference_pi import REPLACEMENTS

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATS_JSON = REPO_ROOT / "data" / "reference" / "ogl" / "feats.json"
REPORT_PATH = REPO_ROOT / "reports" / "pi_feats_triage.md"

# Data della fotografia (stato post-b9f9d63, HEAD 364cd15): il report e'
# un'evidenza puntuale, non un documento vivo.
SNAPSHOT_DATE = "2026-07-19"
SNAPSHOT_HEAD = "364cd15"

# Lista termini PI estesa (75): word-boundary obbligatorio (senza boundary
# "Nex" matcha "next" — motivo dei 227 falsi positivi della scansione grezza).
# UNICA fonte per il triage; Task 3 la unifichera' con tools/legal_filter.py.
# Estensione 2026-07-19 (quality review): +21 termini verificati a mano —
# 17 da review piu' Hermean, Kellid, Mzali, Vudra da sweep word-boundary su
# feats.json. Falsi positivi scartati documentati nel report (Shackles,
# Linnorm, Juju). Candidati cercati a zero hit: elenco in § Copertura.
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

# Sottoinsieme delle deita': un match di questi termini nei prerequisites
# determina la categoria B (prerequisito deita-specifico).
DEITY_TERMS = {
    "sarenrae", "iomedae", "asmodeus", "desna", "calistria", "norgorber",
    "zon-kuthon", "urgathoa", "rovagug", "lamashtu", "abadar", "irori",
    "gozreh", "pharasma", "shelyn", "cayden", "erastil", "torag",
    "besmara", "gorum", "nethys", "walkena",
}

# Regex unica: termini piu' lunghi prima (es. "Pathfinder Society" prima di
# "Pathfinder"), word-boundary su entrambi i lati, case-insensitive.
_PI_RE = re.compile(
    r"\b(?P<term>" + "|".join(re.escape(t) for t in sorted(PI_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# --- Artifact da sanitize storica (categoria D) -----------------------------

# Corruzione testuale nota: "Varisian" -> "a frontier landn" (sostituzione
# naive di "Varisia" dentro la parola). Rileva il replacement incollato a
# lettere residue.
_FRONTIER_LAND_RE = re.compile(r"\ba frontier land[a-z]", re.IGNORECASE)

# Residui dei tag fonte AoN incollati ai nomi feat (es. "TattooISM"):
# "ISM"/"ISWG" sono sigle uppercase, il match case-sensitive evita falsi
# positivi nel testo ordinario (verificato a 0 FP su feats.json 2026-07-19).
_ISM_ISWG_RE = re.compile(r"[A-Za-z]*(?:ISM|ISWG)\b")

# Valori di replacement della sanitize storica: la loro presenza nel NOME
# (case-insensitive) segnala un nome mangiato (es. "Noble Scion a fading
# empire", "Ea bardental Channel" da "Lem"->"a bard" dentro "Elemental").
# La lista dei replacement NON e' duplicata: arriva da
# tools/sanitize_reference_pi.py (fonte unica).
_SANITIZE_VALUES = sorted(
    {new for _, new in REPLACEMENTS if new and new[-1].isalpha()},
    key=len,
    reverse=True,
)

# Esclusioni documentate dalla rilevazione nomi D: nomi AoN legittimi in cui
# un valore di replacement compare per incidente a cavallo di due parole
# reali ("Extr|a Rogue| Talent", "Extr|a Ranger| Trap"). Verificati contro
# l'indice feats AoN in cache (data/reference/aon_cache/19b525ecab068e0c.html).
NAME_ARTIFACT_EXCLUSIONS = {"Extra Rogue Talent", "Extra Ranger Trap"}

# Proposte di ripristino per i nomi corrotti: derivate per reverse-mapping
# della sostituzione naive e verificate contro l'indice feats AoN in cache
# (19b525ecab068e0c.html, 3446 nomi). La git history non aiuta: la
# corruzione e' anteriore al primo commit OGL (596f9df). Il ripristino
# effettivo (Task 2) deve comunque confermare sulla fonte AoN.
RIPRISTINO_PROPOSTO = {
    "Ea bardental Channel": "Elemental Channel",
    "Ea bardental Commixture": "Elemental Commixture",
    "Ea bardental Fist": "Elemental Fist",
    "Ea bardental Focus": "Elemental Focus",
    "Ea bardental Jaunt": "Elemental Jaunt",
    "Ea bardental Knowledge": "Elemental Knowledge",
    "Ea bardental Overload": "Elemental Overload",
    "Ea bardental Spell": "Elemental Spell",
    "Ea bardental Strike": "Elemental Strike",
    "Ea bardental Vigor": "Elemental Vigor",
    "Extra Ea bardental Assault": "Extra Elemental Assault",
    "Flow Of Ea bardents": "Flow of Elements",
    "Greater Ea bardental Focus": "Greater Elemental Focus",
    "Impa bardent Focus": "Implement Focus",
    "Impa bardent Mastery": "Implement Mastery",
    "Incremental Ea bardental Assault": "Incremental Elemental Assault",
    "Noble Scion a fading empire": "Noble Scion (Taldor Variant)",
    "Strong Impa bardent Link": "Strong Implement Link",
    "a god of the hunt's Blessing": "Erastil's Blessing",
    "an ancient desert kingdomology": "Osirionology",
    "an ancient desert kingdomtologist": "Osiriontologist",
    "an explorers' guild Ally": "Pathfinder Society Ally",
}

# Corruzione sistemica delle description (appendice del report, fuori scope
# del triage PI): valore di replacement fuso dentro una parola (lettera
# minuscola subito prima o dopo), es. "ea bardental", "setta bardent",
# "goa bards" (golems), "Arcana barbarianum" (Arcanamirium).
def _merged_word_res():
    for v in _SANITIZE_VALUES:
        yield v, re.compile(r"[a-z]" + re.escape(v) + r"|" + re.escape(v) + r"[a-z]", re.IGNORECASE)

# Esclusioni documentate dalla rilevazione sistemica: testo legittimo.
# - "a bardic performance": inglese corretto (non corruzione);
# - "the Worldwound": testo originale AoN (Vengeful Banisher). "Worldwound"
#   e' dal 2026-07-19 in PI_TERMS, quindi le entry che lo citano sono gia'
#   nel triage; l'esclusione resta come guardia per usi futuri del
#   rilevatore su testi non triagiati.
SYSTEMIC_EXCLUSIONS = [
    re.compile(r"a bardic performance", re.IGNORECASE),
    re.compile(r"the Worldwound", re.IGNORECASE),
]

# Campi scansionati dallo triage (content fields, non metadati).
SCAN_FIELDS = ("name", "prerequisites", "description")

AZIONI = {
    "A": "Spostamento in `pi_local_only/feats_local.json` (identita' PI nel nome; sanitize del nome vietata)",
    "B": "Spostamento in `pi_local_only/feats_local.json` (prerequisito deita-specifico)",
    "C": "Sanitize in place dei campi description/prerequisites (tool word-boundary, Task 2); nessuno spostamento",
    "D": "Ripristino da fonte (cache AoN / re-import), poi ricategorizzazione A/C",
}


def _field_text(entry, field):
    """Testo di un campo: i campi lista sono esaminati per-elemento altrove."""
    value = entry.get(field)
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return value or ""


def _find_terms(text):
    """Termini PI matchati (word-boundary) in text, deduplicati e ordinati."""
    return sorted({m.group("term").lower() for m in _PI_RE.finditer(text)})


def _find_artifacts(entry):
    """Artifact da sanitize storica: lista di (campo, descrizione artifact)."""
    hits = []
    for field in SCAN_FIELDS:
        text = _field_text(entry, field)
        for m in _FRONTIER_LAND_RE.finditer(text):
            hits.append((field, f"corruzione '{m.group(0)}' (Varisia[n] naive)"))
        for m in _ISM_ISWG_RE.finditer(text):
            hits.append((field, f"residuo tag fonte '{m.group(0)}'"))
    name = entry.get("name") or ""
    if name not in NAME_ARTIFACT_EXCLUSIONS:
        for value in _SANITIZE_VALUES:
            if re.search(re.escape(value), name, re.IGNORECASE):
                hits.append(("name", f"nome corrotto: contiene '{value}' (replacement sanitize)"))
                break
    return hits


def _categorize(entry):
    """Restituisce (categoria, match_per_campo, artifact) per una entry."""
    matches = {field: _find_terms(_field_text(entry, field)) for field in SCAN_FIELDS}
    artifacts = _find_artifacts(entry)
    if artifacts:
        return "D", matches, artifacts
    if matches["name"]:
        return "A", matches, artifacts
    prereq_deity = [t for t in matches["prerequisites"] if t in DEITY_TERMS]
    if prereq_deity:
        return "B", matches, artifacts
    if matches["description"] or matches["prerequisites"]:
        return "C", matches, artifacts
    return None, matches, artifacts


def _dangling_refs(entries, targets, triage_names):
    """Riferimenti che lo spostamento renderebbe pendenti.

    Convenzione: match ESATTO case-insensitive del nome entry su ciascun
    elemento di prerequisites/references (convenzione analoga a quella di
    parse_skill per gli header skill, in tools/import_reference.py).
    Segnala a parte i riferimenti "embedded": nome presente con word-boundary
    dentro una stringa piu' lunga (tag incollati tipo "FeatAPG"/"Feat**").
    Esclusi come falsi positivi: stringhe che sono nomi di entry del catalogo
    e stringhe che contengono il nome di un'altra entry piu' lungo del target
    (es. "Aldori Style" dentro "...: Aldori Style Aegis": il riferimento e'
    al feat Aegis, non al target).
    """
    all_names = [e.get("name") or "" for e in entries]
    all_names_lower = {n.lower() for n in all_names}
    result = {}
    for target in targets:
        pat = re.compile(r"\b" + re.escape(target) + r"\b", re.IGNORECASE)
        longer_names = [n for n in all_names
                        if target.lower() in n.lower() and n.lower() != target.lower()]
        exact, embedded = [], []
        for entry in entries:
            other = entry.get("name") or ""
            if other == target:
                continue
            for field in ("prerequisites", "references"):
                items = entry.get(field) or []
                # Guard: campo malformato (non lista) trattato come elemento
                # singolo, senza iterare i caratteri della stringa.
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    s = str(item).strip()
                    if s.lower() == target.lower():
                        exact.append((other, field, s))
                    elif (pat.search(s) and s.lower() not in all_names_lower
                          and not any(re.search(re.escape(n), s, re.IGNORECASE)
                                      for n in longer_names)):
                        embedded.append((other, field, s))
        if exact or embedded:
            result[target] = {"exact": exact, "embedded": embedded,
                              "exact_pending": [x for x in exact if x[0] not in triage_names]}
    return result


def _systemic_corruption(entries, triage_names):
    """Appendice: corruzione sistemica description fuori dal triage PI."""
    pats = list(_merged_word_res())
    hits = {}
    for entry in entries:
        name = entry.get("name") or ""
        if name in triage_names:
            continue
        found = set()
        name_re = re.compile(re.escape(name), re.IGNORECASE)
        for field in ("description", "prerequisites", "references"):
            text = _field_text(entry, field)
            # Il nome proprio dell'entry (ripetuto nelle references) non e'
            # prosa: mascherato per evitare incidenti a cavallo di parole
            # ("Extr|a Rogue| Talent"), gia' gestiti dal rilevatore nomi D.
            text = name_re.sub("", text)
            for excl in SYSTEMIC_EXCLUSIONS:
                text = excl.sub("", text)
            for value, pat in pats:
                if pat.search(text):
                    found.add(value)
        if found:
            hits[name] = sorted(found)
    return hits


def build_triage(entries):
    """Scansione completa: righe triage ordinate, dangling refs, appendice."""
    rows = []
    for entry in entries:
        category, matches, artifacts = _categorize(entry)
        if category is None:
            continue
        rows.append({
            "name": entry.get("name") or "",
            "category": category,
            "matches": matches,
            "artifacts": artifacts,
        })
    rows.sort(key=lambda r: (r["category"], r["name"].lower()))
    triage_names = {r["name"] for r in rows}
    # Dangling refs per A/B (da piano) e D (si spostano anch'esse, Task 2).
    targets = [r["name"] for r in rows if r["category"] in ("A", "B", "D")]
    dangling = _dangling_refs(entries, targets, triage_names)
    systemic = _systemic_corruption(entries, triage_names)
    return rows, dangling, systemic


def _fmt_matches(row):
    parts = []
    labels = {"name": "name", "prerequisites": "prereq", "description": "desc"}
    for field in SCAN_FIELDS:
        terms = row["matches"][field]
        if terms:
            parts.append(f"{labels[field]}: {', '.join(terms)}")
    return "<br>".join(parts) or "—"


def _fmt_artifacts(row):
    return "<br>".join(f"{field}: {desc}" for field, desc in row["artifacts"])


def _fmt_dangling(name, dangling, triage_names):
    info = dangling.get(name)
    if not info:
        return "—"
    parts = []
    for other, field, _s in sorted(info["exact"], key=lambda x: x[0].lower()):
        nota = " (nel triage: si sposta anch'essa)" if other in triage_names else " **PENDENTE**"
        parts.append(f"{other} [{field}]{nota}")
    for other, field, s in sorted(info["embedded"], key=lambda x: x[0].lower()):
        parts.append(f"{other} [{field}, embedded: `{s[:60]}`]")
    return "<br>".join(parts)


def render_report(rows, dangling, systemic, total_entries):
    """Report markdown in italiano (evidenza della decisione policy)."""
    by_cat = {c: [r for r in rows if r["category"] == c] for c in "ABCD"}
    n_term_matches = sum(1 for r in rows if any(r["matches"][f] for f in SCAN_FIELDS))
    out = []
    add = out.append
    add("# Triage PI feats preesistenti — " + SNAPSHOT_DATE)
    add("")
    add(f"> Generato da `tools/triage_pi_feats.py --write`. Fotografia di "
        f"`data/reference/ogl/feats.json` ({total_entries} entry) allo stato "
        f"post-`b9f9d63` (HEAD `{SNAPSHOT_HEAD}`). Evidenza della decisione "
        f"policy di `planning/2026-07-19-pi-feats-triage.md`.")
    add("")
    add("## Metodo")
    add("")
    add(f"- **Lista termini**: {len(PI_TERMS)} termini PI (toponimi/etnie/deita'/organizzazioni "
        "Golarion-specifici), match **word-boundary** "
        "case-insensitive su un'unica regex. Il boundary e' obbligatorio: "
        "senza, \"Nex\" matcha \"next\" (motivo dei 227 falsi positivi della "
        "prima scansione grezza). Criterio di completezza e sweep in "
        "§ Copertura della lista.")
    add("- **Campi scansionati**: `name`, `prerequisites`, `description`.")
    add("- **Categorie** (in conflitto vince la piu' severa, D > A > B > C):")
    add("  - **A** — match PI nel nome: identita' PI → `pi_local_only` (sanitize del nome vietata).")
    add("  - **B** — match di una deita' nei prerequisites: prerequisito deita-specifico → `pi_local_only`.")
    add("  - **C** — match solo in description, o PI non-deita' nei prerequisites → sanitize in place.")
    add("  - **D** — artifact da sanitize storica naive (nomi corrotti, residui ISM/ISWG, "
        "pattern \"a frontier landn\") → ripristino da fonte, poi ricategorizzazione.")
    add("- **Dangling refs**: match esatto case-insensitive del nome entry sugli elementi di "
        "`prerequisites`/`references` delle altre entry (convenzione analoga a "
        "quella di `parse_skill` per gli header skill, in `tools/import_reference.py`). "
        "I riferimenti *embedded* (tag incollati tipo "
        "`FeatAPG`, separatori `**`) sono segnalati a parte: non emergono con il match esatto.")
    add("")
    add("## Conteggi")
    add("")
    add("| Categoria | Entry | Destinazione policy |")
    add("| --- | ---: | --- |")
    add(f"| A — PI nel nome | {len(by_cat['A'])} | `pi_local_only/feats_local.json` |")
    add(f"| B — deita' nei prerequisites | {len(by_cat['B'])} | `pi_local_only/feats_local.json` |")
    add(f"| C — solo description / prereq non-deita' | {len(by_cat['C'])} | sanitize in place |")
    add(f"| D — artifact sanitize storica | {len(by_cat['D'])} | ripristino → ricategorizzazione |")
    add(f"| **Totale righe triage** | **{len(rows)}** | |")
    add("")
    add(f"**Confronto con la misura di riferimento (41)**: la misura del "
        f"controller usava la lista a 54 termini. Con la lista estesa a "
        f"**{len(PI_TERMS)} termini** (quality review 2026-07-19, § Copertura "
        f"della lista) le entry con almeno un match lessicale salgono a "
        f"**{n_term_matches}** (+{n_term_matches - 41}, tutte da termini "
        f"aggiunti). A queste il triage aggiunge **{len(rows) - n_term_matches} "
        "entry di categoria D** il cui nome, corrotto dalla sanitize storica, "
        "non contiene piu' alcun termine PI e sfugge quindi al match lessicale "
        "(es. \"Ea bardental Channel\", in origine \"Elemental Channel\"). "
        f"Totale righe in triage: {n_term_matches} + "
        f"{len(rows) - n_term_matches} = **{len(rows)}**. Dettaglio in "
        "§ Note e scarti.")
    add("")
    add("## Copertura della lista")
    add("")
    add("**Criterio di completezza**: un termine entra in lista se e' un "
        "toponimo / etnia / deita' / organizzazione **specifico di Golarion** "
        "(fonte canonica: AoN/indice feats in cache), con match word-boundary "
        "case-insensitive, e ogni hit e' verificato a mano contro falsi "
        "positivi prima dell'inclusione. La lista vive in un punto solo "
        "(`PI_TERMS` nel tool); Task 3 la unifichera' con `legal_filter.py`.")
    add("")
    add("**Estensione 2026-07-19** (quality review): 17 termini mandati "
        "(Lastwall, Worldwound, Belkzen, Shoanti, Mwangi, Tian, Varisian, "
        "Chelish, Irrisen, Galt, Hermea, Alkenstar, Korvosa, Riddleport, "
        "Daggermark, River Kingdoms, Walkena) + 4 da sweep verificato "
        "(**Hermean** — necessario per `Hermean Blood`, \\bHermea\\b non "
        "matcha \"Hermean\"; **Kellid**, **Mzali**, **Vudra**). Walkena "
        "entra anche in `DEITY_TERMS` (deita' Mwangi → categoria B).")
    add("")
    add("**Sweep eseguito**: ~60 candidati (toponimi Inner Sea e oltre, "
        "etnie, deita' minori, demon lord, archdevil) cercati word-boundary "
        "su `feats.json`. A **zero hit nei campi scansionati** "
        "(name/prerequisites/description) del catalogo corrente (non in "
        "lista; candidati naturali per il gate di Task 3 i toponimi sicuri): "
        "Magnimar, Nirmathas, Molthune, Brevoy, Sandpoint, Cassomir, "
        "Ostenso, Westcrown, Egorian, Almas, Sothis, Mendev, Sarkoris, "
        "Vudran, Jalmeray, Iobaria, Kalabuto, Bloodcove, Eleder, Usaro, "
        "Garund, Avistan, Mbeke, Taralu, Azlant, Thassilon, Xin, Aroden; "
        "demon lord/archdevil: Deskari, Baphomet, Pazuzu, Nocticula, Zura, "
        "Cyth-V'sug, Moloch, Belial, Dispater, Mammon, Geryon, Baalzebul, "
        "Mephistopheles (nomi anche mitologici generici: a maggior ragione "
        "fuori dalla lista corrente, rischio FP in altri cataloghi/testi). "
        "Nota: **Sargava** ha hit solo nei metadati `source`/`source_id` "
        "(titolo del libro \"Sargava, The Lost Colony\" di 5 entry), zero "
        "nei campi scansionati: non in lista.")
    add("")
    add("**Falsi positivi scartati** (hit verificati a mano, termine NON "
        "aggiunto):")
    add("- **Shackles** — 5 hit, tutti il sostantivo comune \"catene\" "
        "(`Falcon's Cry` \"shackles of oppression\", `Free Spirit` e `Heroic "
        "Will` \"mental shackles\", `Hellish Shackles` \"shackles of Hell\", "
        "`Liberator` \"in shackles\"), mai la nazione pirata \"The Shackles\".")
    add("- **Linnorm** — 3 hit (`Linnorm Style`, `Linnorm Vengeance`, `Linnorm "
        "Wrath`): tipo di creatura (drago norreno), non il regno dei Linnorm "
        "Kings.")
    add("- **Juju** — 3 hit: termine ambiguo (parola d'uso comune inglese + "
        "creatura \"juju zombie\" in `Improved Death-Stealing`). Le entry "
        "della religione Mwangi restano coperte dai termini gia' in lista: "
        "`Juju Way` via \"Mwangi\" (prereq), `Mark Of The Devoted` via "
        "\"Mwangi\"/\"Walkena\"/\"Mzali\". `Improved Death-Stealing` (prereq "
        "creatura Nabasu) non e' PI-identity: esclusa.")
    add("- **Tian** — mantenuto: etnia canonica di Golarion; il word-boundary "
        "protegge dai match dentro altre parole (nessun FP osservato).")
    add("")

    cat_titles = {
        "A": "Categoria A — PI nel nome",
        "B": "Categoria B — deita' nei prerequisites",
        "C": "Categoria C — match solo in description / prereq non-deita'",
        "D": "Categoria D — artifact da sanitize storica",
    }
    for cat in "ABCD":
        rows_cat = by_cat[cat]
        add(f"## {cat_titles[cat]} ({len(rows_cat)})")
        add("")
        # Azione proposta in legenda di sezione (valida per tutte le righe),
        # non ripetuta per riga.
        add(f"**Azione proposta (tutta la categoria)**: {AZIONI[cat]}.")
        add("")
        if not rows_cat:
            add("_Nessuna entry._")
            add("")
            continue
        if cat == "D":
            add("| Entry (stato corrente) | Artifact | Ripristino proposto | Dangling refs |")
            add("| --- | --- | --- | --- |")
            for r in rows_cat:
                restored = RIPRISTINO_PROPOSTO.get(r["name"], "— (ripristino testo, nome intatto)")
                add(f"| {r['name']} | {_fmt_artifacts(r)} | {restored} | "
                    f"{_fmt_dangling(r['name'], dangling, {rr['name'] for rr in rows})} |")
        else:
            add("| Entry | Match (campi) | Dangling refs |")
            add("| --- | --- | --- |")
            for r in rows_cat:
                add(f"| {r['name']} | {_fmt_matches(r)} | "
                    f"{_fmt_dangling(r['name'], dangling, {rr['name'] for rr in rows})} |")
        add("")

    add("## Riferimenti pendenti (dangling refs) — dettaglio")
    add("")
    pending_lines = []
    for target in sorted(dangling, key=str.lower):
        info = dangling[target]
        for other, field, s in info["exact_pending"]:
            pending_lines.append((target, other, field, s))
    if pending_lines:
        add("Riferimenti **esatti** da entry che resterebbero nel catalogo OGL "
            "verso entry A/B/D destinate a `pi_local_only` (lo spostamento li "
            "rende pendenti; gestione da policy §5: strip con nota o spostamento a cascata):")
        add("")
        for target, other, field, s in sorted(pending_lines, key=lambda x: (x[0].lower(), x[1].lower())):
            add(f"- `{other}` → `{target}` (campo `{field}`: \"{s}\")")
    else:
        add("Nessun riferimento esatto pendente: tutti i riferimenti esatti ad "
            "entry A/B/D provengono da entry a loro volta nel triage (si "
            "spostano/sanitizzano insieme).")
    add("")
    embed_lines = [(t, o, f, s) for t in dangling for (o, f, s) in dangling[t]["embedded"]]
    if embed_lines:
        add("Riferimenti **embedded** (non esatti: tag fonte incollati o "
            "separatori `**`; il match esatto della policy non li vede — "
            "rilevanti per il ripristino dei nomi D):")
        add("")
        for target, other, field, s in sorted(embed_lines, key=lambda x: (x[0].lower(), x[1].lower())):
            add(f"- `{other}` → `{target}` (campo `{field}`: \"{s[:80]}\")")
    add("")

    add("## Appendice — corruzione sistemica delle description (fuori scope triage PI)")
    add("")
    add(f"La sanitize storica naive ha sostituito i nomi degli iconici "
        f"(\"Lem\" → \"a bard\", ecc.) **dentro le parole**: \"elemental\" → "
        f"\"ea bardental\", \"settlement\" → \"setta bardent\", \"implement\" → "
        f"\"impa bardent\", \"golems\" → \"goa bards\", \"Arcanamirium\" → "
        f"\"Arcana barbarianum\". Oltre alle entry D gia' in tabella, "
        f"**{len(systemic)} entry** (senza rilevanza PI: nessun match di "
        f"termine, nome intatto) hanno description/prerequisites/references "
        f"corrotti da questa classe. Non entrano nella decisione policy A/B/C ma sono "
        f"evidenza per un ripristino sistematico delle description da fonte "
        f"(decisione del controller: estensione Task 2 o task dedicato).")
    add("")
    add("Stessa classe, nei `references` di quasi tutto il catalogo: "
        "\"Archives of a deity of magic\" — il replacement \"Nethys\" → \"a "
        "deity of magic\" e' applicato **prima** di \"Archives of Nethys\" → "
        "\"Pathfinder PRD\" nell'ordine di `REPLACEMENTS`, quindi la regola "
        "frase-level non scatta mai. Non e' corruzione del contenuto (solo "
        "riferimento fonte), ma va corretta nell'ordine delle sostituzioni "
        "del tool sanitize (Task 2).")
    add("")
    add("<details><summary>Elenco entry (nomi)</summary>")
    add("")
    add(", ".join(sorted(systemic, key=str.lower)))
    add("")
    add("</details>")
    add("")

    add("## Note e scarti rispetto al piano")
    add("")
    add("- **Scarto conteggio**: la misura di riferimento del controller (41) "
        "contava i match lessicali word-boundary della lista a 54 termini; "
        "il triage li riproduce esattamente (le 20 entry aggiunte ai match "
        "lessicali provengono tutte dai 21 termini dell'estensione quality "
        "review, § Copertura della lista) e vi aggiunge le entry D senza match "
        "lessicale residuo (nomi corrotti da \"Lem\"→\"a bard\", \"Osirion\"→"
        "\"an ancient desert kingdom\", \"Erastil's\"→\"a god of the hunt's\", "
        "\"Pathfinder Society\"→\"an explorers' guild\"). Il tool ha ragione: "
        "lo scarto e' ri-derivato riga per riga nelle tabelle sopra.")
    add("- **Ricategorizzazioni rispetto alla stima preliminare del piano**:")
    add("  - `Eye of the Arclord`: match \"Nex\" in description (non nel nome) → **C**, "
        "come previsto dal piano (\"verificare\").")
    add("  - `Noble Scion a fading empire`: il piano la citava tra i nomi A; "
        "avendo artifact nel nome e' **D** (vince la piu' severa). Ripristino "
        "proposto: \"Noble Scion (Taldor Variant)\" (nome AoN da indice in "
        "cache; il piano citava \"Noble Scion of Taldor\", forma d20pfsrd — "
        "confermare su fonte in Task 2).")
    add("  - I feat delle famiglie Aldori/Hellknight **senza** il termine nel "
        "nome letterale (`Duelist Of The Roaring Falls`, `Ominous Mien`, "
        "`Signifer Armor Training`, ecc. — il piano li elencava nel bucket A "
        "per famiglia) ricadono in **C** per la regola stretta \"A = match "
        "nel nome\". Nota policy: la loro description/prereq contiene il "
        "termine PI e i prereq referenziano feat A in partenza (vedi dangling "
        "refs): valutare in Task 2 se trattarli come famiglia (spostamento a "
        "cascata, policy §5) invece che sanitize C.")
    add("- **Residui ISM**: `b9f9d63` ha pulito \"a frontier landn\" e "
        "\"TattooISWG\", ma resta \"Inscribe Magical TattooISM\" (tag ISM "
        "incollato) nei prerequisites di `Tattoo Attunement` e `Tattoo "
        "Transformation` → **D** (ripristino testo; post-ripristino escono "
        "dal triage: nessun PI).")
    add("- **Raddoppi da sanitize parziale**: alcune C con \"inner sea\" "
        "(es. `Scholar`: \"throughout the the inner sea region region\") "
        "sono gia' state sanitize una volta in modo naive (\"Inner Sea "
        "region\" → \"the inner sea region region\") e contengono ancora il "
        "termine. La sanitize word-boundary di Task 2 deve essere "
        "**idempotente**: risostituire \"inner sea\" dentro \"the inner sea "
        "region\" produrrebbe un'ulteriore incollatura.")
    add("- **Falsi positivi esclusi** (documentati nel tool): `Extra Rogue "
        "Talent`, `Extra Ranger Trap` (nomi legittimi: \"a rogue\"/\"a ranger\" "
        "a cavallo di \"Extra Rogue|Ranger\"); \"a bardic performance\" "
        "(inglese corretto) nell'appendice sistemica. I FP dello sweep "
        "termini (Shackles, Linnorm, Juju) sono in § Copertura della lista.")
    add("- **Duplicato `LastwallPhalanx`**: entry distinta da `Lastwall "
        "Phalanx` con nome incollato (artifact di import, non da sanitize) "
        "e description identica. La regola stretta la classifica **C** "
        "(match \"Belkzen\" in description; \\bLastwall\\b non matcha il nome "
        "incollato), ma l'identita' e' PI: in Task 2 valutare dedup + "
        "trattamento come `Lastwall Phalanx` (A).")
    add("- **Git history non utilizzabile per il ripristino**: la corruzione "
        "e' anteriore al primo commit OGL (`596f9df`); i nomi originali "
        "proposti sono verificati contro l'indice feats AoN in cache "
        "(`data/reference/aon_cache/19b525ecab068e0c.html`, 3446 nomi).")
    add("")

    add("## Verifiche manuali a campione")
    add("")
    add(f"Campioni verificati a mano contro `feats.json` allo stato "
        f"fotografato (HEAD `{SNAPSHOT_HEAD}`, {SNAPSHOT_DATE}). Evidenza "
        "riproducibile: `python tools/triage_pi_feats.py --write` rigenera "
        "deterministicamente questo report dagli stessi dati.")
    add("")
    add("1. **`Aldori Dueling Disciple` (A)**: \"Aldori\" in name, prereq e "
        "description; referenziata esattamente dai prerequisites di `Duelist "
        "Of The Roaring Falls`, `Duelist Of The Shrouded Lake`, `Falling "
        "Water Gambit` (tutte C: dangling interno al triage).")
    add("2. **`Squash Flat` (B)**: \"Rovagug\" nei prerequisites "
        "(\"worshiper of Rovagug\"); referenzia esattamente `Merciless Rush` "
        "(B): dangling interno, si spostano insieme.")
    add("3. **`Ea bardental Channel` (D)**: nessun match lessicale; nome con "
        "\"a bard\" (Lem→a bard dentro \"Elemental\"); originale \"Elemental "
        "Channel\" confermato nell'indice AoN in cache; description con "
        "\"ea bardental subtype\" (stessa corruzione).")
    add("4. **`Scholar` (C)**: match \"inner sea\" solo in description; "
        "nessun dangling ref.")
    add("5. **`Lastwall Phalanx` (A, estensione)**: \"Lastwall\" nel nome, "
        "\"Belkzen\" in description; duplicato `LastwallPhalanx` tracciato "
        "in § Note.")
    add("6. **`Mark Of The Devoted` (B, estensione)**: prereq \"Walkena "
        "worshiper\" (deita' Mwangi) + \"human of Mwangi ethnicity\"; "
        "\"Mzali\" in description.")
    add("")
    return "\n".join(out) + "\n"


def main():
    # Console Windows cp1252: il report contiene '→' e simili; forza UTF-8
    # in modalita' stdout (guardato: reconfigure esiste solo su py3.7+).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help=f"scrive il report in {REPORT_PATH.relative_to(REPO_ROOT)}")
    args = parser.parse_args()

    try:
        data = json.loads(FEATS_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[triage] ERRORE: file non trovato: {FEATS_JSON}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"[triage] ERRORE: JSON non valido in {FEATS_JSON}: {exc}", file=sys.stderr)
        return 1
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        print(f"[triage] ERRORE: chiave 'entries' assente o non lista in {FEATS_JSON}",
              file=sys.stderr)
        return 1
    rows, dangling, systemic = build_triage(entries)
    report = render_report(rows, dangling, systemic, len(entries))

    counts = {c: sum(1 for r in rows if r["category"] == c) for c in "ABCD"}
    n_term = sum(1 for r in rows if any(r["matches"][f] for f in SCAN_FIELDS))
    if args.write:
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"Report scritto: {REPORT_PATH.relative_to(REPO_ROOT)}")
    else:
        print(report, end="")
    print(f"[triage] entry={len(entries)} match_termini={n_term} "
          f"A={counts['A']} B={counts['B']} C={counts['C']} D={counts['D']} "
          f"totale={len(rows)} appendice_sistemica={len(systemic)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
