#!/usr/bin/env python3
"""Sanitizza Product Identity note dai cataloghi OGC.

Applica sostituzioni testuali conservative sui campi di contenuto e sui
riferimenti fonte dei cataloghi in data/reference/ogl/.

Fix 2026-07-19 (Task 2 policy PI feats, planning/2026-07-19-pi-feats-triage.md):
- Match **word-boundary** (lookaround ``(?<!\\w)`` / ``(?!\\w)``): la versione
  naive sostituiva sottostringhe e ha corrotto il catalogo ("Lem" -> "a bard"
  dentro "elemental" -> "ea bardental", "Varisia" dentro "Varisian" ->
  "a frontier landn"). I boundary reggono anche i termini con apostrofo
  finale ("Sodden Lands'").
- Ordine **frasi prima delle parole** (lunghezza decrescente): "Archives of
  Nethys" -> "Pathfinder PRD" ora scatta prima di "Nethys" -> "a deity of
  magic" (bug storico: "Archives of a deity of magic" in tutto il catalogo).
- **Idempotenza**: se il replacement contiene il termine (es. "Inner Sea" ->
  "the inner sea region"), il match dentro il contesto gia' sostituito e'
  escluso con guardie lookaround derivate dal replacement stesso: il testo
  gia' sanitize non viene raddoppiato. Le regole "the the inner sea region
  [region]" riparano il raddoppio storico gia' presente nel catalogo.
- Il campo **name non e' mai sanitizzato** (policy: le entry con PI nel nome
  vanno in pi_local_only; sanitize del nome vietata). Campi tecnici
  (_license, _source, source, source_id, reference_urls, timestamp) intoccati.
- I termini aggiunti per il Task 2 (DESCRIPTION_ONLY_REPLACEMENTS: Aldori,
  Hellknight, Nex, ...) si applicano **solo al campo description** e **solo
  su richiesta esplicita** (``sanitize_text(..., description=True)`` /
  ``sanitize_entry(..., description_only=True)``): sono per l'uso chirurgico
  di tools/apply_pi_feats_policy.py. ``main()`` (run repo-wide su tutti i
  cataloghi OGL) applica **solo le sostituzioni base REPLACEMENTS**
  word-boundary e NON le regole description-only (fix quality review
  2026-07-19: evitare che "Aldori" & co. vengano neutralizzati nelle
  description di equipment/traits/... in un run indiscriminato).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OGL_DIR = REPO_ROOT / "data" / "reference" / "ogl"

# Sostituzioni PI -> testo neutro. Ordinate per priorità (frasi prima delle parole).
# NOTA: l'ordine applicativo effettivo e' per lunghezza decrescente del
# termine (vedi _compile_rules); l'ordine qui sotto e' storico/redazionale.
REPLACEMENTS = [
    # Frasi / titoli di prodotti
    ("Pathfinder Society Primer", "Explorer's Primer"),
    ("Pathfinder Society", "an explorers' guild"),
    ("Cheliax, Empire of Devils", "A Diabolic Empire"),
    ("Cheliax Empire Of Devils", "A Diabolic Empire"),
    ("Andoran, Spirit of Liberty", "A Spirit of Liberty"),
    ("Andoran Spirit Of Liberty", "A Spirit of Liberty"),
    ("Dwarves of Golarion", "Dwarves of the World"),
    ("Gnomes of Golarion", "Gnomes of the World"),
    ("Goblins of Golarion", "Goblins of the World"),
    ("Halflings of Golarion", "Halflings of the World"),
    ("Orcs of Golarion", "Orcs of the World"),
    ("Kobolds of Golarion", "Kobolds of the World"),
    ("Bastards of Golarion", "Bastards of the World"),
    ("Mana Wastes", "a magic-blasted wasteland"),
    # "Inner Sea": forma canonica del replacement "the inner sea region".
    # Le regole lunghe (raddoppi storici e forme con articolo) precedono
    # quella breve grazie all'ordinamento per lunghezza; le guardie di
    # idempotenza impediscono di raddoppiare il testo gia' sanitize.
    ("the the inner sea region region", "the inner sea region"),
    ("the the inner sea region", "the inner sea region"),
    ("the inner sea region", "the inner sea region"),
    # Varianti con "an": evitano il raddoppio d'articolo ("an the inner sea
    # region") — fissate da test (quality review 2026-07-19).
    ("an inner sea region", "the inner sea region"),
    ("an inner sea", "the inner sea region"),
    ("inner sea region", "the inner sea region"),
    ("the inner sea", "the inner sea region"),
    ("Inner Sea", "the inner sea region"),
    # Iconici
    ("Ezren", "a wizard"),
    ("Seelah", "a paladin"),
    ("Valeros", "a fighter"),
    ("Merisiel", "a rogue"),
    ("Kyra", "a cleric"),
    ("Harsk", "a ranger"),
    ("Lem", "a bard"),
    ("Sajan", "a monk"),
    ("Amiri", "a barbarian"),
    ("Lini", "a druid"),
    # Nomi propri di setting / divinità
    ("Absalom", "a great city"),
    ("Andoran", "a free nation"),
    ("Asmodeus", "a tyrant god"),
    ("Calistria", "a goddess of lust and revenge"),
    ("Cayden Cailean", "a freedom deity"),
    ("Cayden", "a freedom deity"),
    ("Cheliax", "a diabolic empire"),
    ("Desna", "a goddess of dreams"),
    ("Druma", "a merchant principality"),
    ("Erastil", "a god of the hunt"),
    ("Golarion", "the world"),
    ("Iomedae", "a goddess of valor"),
    ("Katapesh", "a merchant nation"),
    ("Kyonin", "an elven realm"),
    ("Nethys", "a deity of magic"),
    ("Norgorber", "a god of secrets"),
    ("Numeria", "a realm of lost technology"),
    ("Osirion", "an ancient desert kingdom"),
    # Variante di "Osirion" (quality review Task 3): stessa forma neutra.
    ("Osiria", "an ancient desert kingdom"),
    ("Oppara", "a capital city"),
    ("Pharasma", "a goddess of fate"),
    ("Qadira", "a desert kingdom"),
    ("Sarenrae", "a sun goddess"),
    ("Shelyn", "a goddess of beauty"),
    ("Sodden Lands", "a storm-ravaged coast"),
    ("Taldor", "a fading empire"),
    ("Torag", "a god of the forge"),
    ("Ustalav", "a haunted land"),
    ("Urgathoa", "a goddess of undeath"),
    ("Varisia", "a frontier land"),
    ("Zon-Kuthon", "a dark god"),
    ("Besmara", "a pirate goddess"),
    ("Abadar", "a god of cities"),
    ("Gorum", "a god of war"),
    ("Irori", "a god of perfection"),
    # Forme possessive
    ("Andoran's", "a free nation's"),
    ("Asmodeus's", "a tyrant god's"),
    ("Calistria's", "a goddess of lust and revenge's"),
    ("Cayden Cailean's", "a freedom deity's"),
    ("Cayden's", "a freedom deity's"),
    ("Cheliax's", "a diabolic empire's"),
    ("Desna's", "a goddess of dreams's"),
    ("Druma's", "a merchant principality's"),
    ("Erastil's", "a god of the hunt's"),
    ("Golarion's", "the world's"),
    ("Iomedae's", "a goddess of valor's"),
    ("Katapesh's", "a merchant nation's"),
    ("Kyonin's", "an elven realm's"),
    ("Nethys's", "a deity of magic's"),
    ("Norgorber's", "a god of secrets's"),
    ("Numeria's", "a realm of lost technology's"),
    ("Osirion's", "an ancient desert kingdom's"),
    ("Oppara's", "a capital city's"),
    ("Pharasma's", "a goddess of fate's"),
    ("Qadira's", "a desert kingdom's"),
    ("Sarenrae's", "a sun goddess's"),
    ("Shelyn's", "a goddess of beauty's"),
    ("Sodden Lands'", "a storm-ravaged coast's"),
    ("Taldor's", "a fading empire's"),
    ("Torag's", "a god of the forge's"),
    ("Ustalav's", "a haunted land's"),
    ("Urgathoa's", "a goddess of undeath's"),
    ("Varisia's", "a frontier land's"),
    ("Zon-Kuthon's", "a dark god's"),
    ("Besmara's", "a pirate goddess's"),
    ("Abadar's", "a god of cities's"),
    ("Gorum's", "a god of war's"),
    ("Irori's", "a god of perfection's"),
    # Personaggi (possessivi)
    ("Ezren's", "a wizard's"),
    ("Seelah's", "a paladin's"),
    ("Valeros's", "a fighter's"),
    ("Merisiel's", "a rogue's"),
    ("Kyra's", "a cleric's"),
    ("Harsk's", "a ranger's"),
    ("Lem's", "a bard's"),
    ("Sajan's", "a monk's"),
    ("Amiri's", "a barbarian's"),
    ("Lini's", "a druid's"),
    # Fonti: sostituire nome del sito PI nei riferimenti
    ("Archives of Nethys", "Pathfinder PRD"),
    # Personaggi noti extra
    ("Maxillar Pythareus", "a noble scion"),
    ("Pythareus", "a noble scion"),
]

# Termini aggiunti dal Task 2 (planning/2026-07-19-pi-feats-triage.md):
# applicati SOLO al campo description (mai name/prerequisites). Coprono i
# match description delle entry categoria C del triage piu' i termini
# pianificati (Nex, Geb, Nidal, Rahadoum/i, Thuvia/n, Taldan, Chelish/
# Chelaxian, Andoren, Aldori, Gozreh, Rovagug, Lamashtu). Le forme con
# articolo ("an Aldori dueling sword", "a Hellknight", "the Worldwound")
# evitano "an dueling sword" / "as a a knight..." / "the a demon-...".
DESCRIPTION_ONLY_REPLACEMENTS = [
    ("an Aldori dueling sword", "a dueling sword"),
    ("Aldori dueling sword", "dueling sword"),
    ("Aldori", "dueling"),
    ("a Hellknight", "a knight of a strict order"),
    ("Hellknight", "a knight of a strict order"),
    ("the Worldwound", "a demon-blighted land"),
    ("Worldwound", "a demon-blighted land"),
    ("Shoanti tribe", "tribe"),
    ("Shoanti", "tribal"),
    ("Nex", "a mage-ruled realm"),
    ("Geb", "an undead-ruled land"),
    ("Nidal", "a shadow-bound land"),
    ("Rahadoumi", "godless"),
    ("Rahadoum", "a godless nation"),
    ("Thuvian", "sun-scorched"),
    ("Thuvia", "a sun-scorched land"),
    ("Taldan", "imperial"),
    ("Chelaxian", "diabolic"),
    ("Chelish", "diabolic"),
    ("Andoren", "free"),
    ("Varisian", "frontier"),
    ("Irrisen", "a winter-locked realm"),
    ("Galt", "a revolution-torn land"),
    ("Alkenstar", "a gunpowder city"),
    ("Korvosa", "a port city"),
    ("Riddleport", "a pirate port"),
    ("Mwangi", "jungle-born"),
    ("Gozreh", "a god of nature"),
    ("Rovagug", "a god of destruction"),
    ("Lamashtu", "a goddess of monsters"),
    # Task 3 esteso (policy traits 2026-07-19): "Aroden's" e' coperto dal
    # boundary (l'apostrofo resta fuori dal match); "Arodenite" NON matcha
    # (boundary: le entry "Arodenite*" sono PI-identity -> pi_local_only).
    ("Aroden", "a dead god"),
    ("Sothis", "a desert metropolis"),
]

# Campi mai sanitizzati: il nome (policy: le entry PI-identita' vanno in
# pi_local_only, la sanitize del nome e' vietata) e i metadati tecnici/legali.
SKIP_FIELDS = {
    "name", "_license", "_source", "source", "source_id", "reference_urls",
    "updated_at", "created_at",
}


def _compile_rules(rules):
    """Compila le regole (old, new) in regex ordinate per lunghezza decrescente.

    Boundary via lookaround (regge gli apostrofi finali). Se il replacement
    contiene il termine (match word-boundary case-insensitive, prima
    occorrenza), il contesto del replacement (prefisso/suffisso letterali)
    diventa guardia: il testo gia' sanitize non viene risostituito
    (idempotenza, es. "Inner Sea" dentro "the inner sea region").
    """
    compiled = []
    for old, new in sorted(rules, key=lambda r: (-len(r[0]), r[0].lower())):
        lookbehind = lookahead = ""
        m = re.search(r"(?<!\w)" + re.escape(old) + r"(?!\w)", new, re.IGNORECASE)
        if m:
            prefix, suffix = new[:m.start()], new[m.end():]
            if prefix:
                lookbehind = "(?<!" + re.escape(prefix) + ")"
            if suffix:
                lookahead = "(?!" + re.escape(suffix) + ")"
        pattern = re.compile(
            lookbehind + r"(?<!\w)" + re.escape(old) + r"(?!\w)" + lookahead,
            re.IGNORECASE,
        )
        compiled.append((old, pattern, new))
    return compiled


_RULES = _compile_rules(REPLACEMENTS)
_RULES_DESCRIPTION = _compile_rules(DESCRIPTION_ONLY_REPLACEMENTS)


def sanitize_text(text: str, description: bool = False) -> str:
    """Applica le sostituzioni PI a una stringa (word-boundary, idempotente).

    Con description=True applica anche DESCRIPTION_ONLY_REPLACEMENTS (termini
    consentiti solo nelle description per policy Task 2).
    """
    for _old, pattern, new in _RULES:
        text = pattern.sub(new, text)
    if description:
        for _old, pattern, new in _RULES_DESCRIPTION:
            text = pattern.sub(new, text)
    return text


def _sanitize_value(value, description: bool = False):
    if isinstance(value, str):
        return sanitize_text(value, description=description)
    if isinstance(value, list):
        return [_sanitize_value(item, description=description) for item in value]
    if isinstance(value, dict):
        return {k: _sanitize_value(v, description=description) for k, v in value.items()}
    return value


def sanitize_entry(entry: dict, description_only: bool = True) -> dict:
    """Copia sanitizzata di una entry di catalogo.

    Il campo name e i campi tecnici/legali non vengono toccati. Con
    description_only=True (default: uso chirurgico, es. apply_pi_feats_policy)
    al campo description si applicano anche i termini description-only; con
    False solo le sostituzioni base REPLACEMENTS.
    """
    result = {}
    for key, value in entry.items():
        if key in SKIP_FIELDS:
            result[key] = value
        elif key == "description":
            result[key] = _sanitize_value(value, description=description_only)
        else:
            result[key] = _sanitize_value(value, description=False)
    return result


def _sanitize(obj, is_root: bool = True, description_only: bool = False):
    """Forma generica ricorsiva (usata da main): stessa logica di
    sanitize_entry applicata a qualsiasi struttura JSON. Di default NON
    applica le regole description-only (main() e' repo-wide)."""
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, list):
        return [_sanitize(item, is_root=False, description_only=description_only)
                for item in obj]
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in SKIP_FIELDS:
                result[key] = value
            elif key == "description":
                result[key] = _sanitize_value(value, description=description_only)
            else:
                result[key] = _sanitize(value, is_root=False,
                                        description_only=description_only)
        return result
    return obj


def main() -> int:
    """Run repo-wide sui cataloghi OGL: applica SOLO le sostituzioni base
    REPLACEMENTS (word-boundary). Le regole description-only sono escluse:
    restano ad uso chirurgico via apply_pi_feats_policy."""
    changed_files = 0
    for path in sorted(OGL_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sanitized = _sanitize(data, is_root=True, description_only=False)
        if sanitized != data:
            path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
            changed_files += 1
            print(f"Sanitizzato: {path.name}")
    print(f"File modificati: {changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
