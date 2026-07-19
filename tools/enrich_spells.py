"""Arricchisce data/reference/ogl/spells.json con il campo `mechanics`.

Strategia offline, due fonti combinate:
1. join per nome normalizzato con la cache gist PathfinderSpellsJSON
   (.cache/enrichment/), che ha campi strutturati (school, components, ...);
2. fallback regex sulla `description` testuale, sia in formato riga singola
   ("School evocation [fire]; Level sorcerer/wizard 3. Casting Time ...")
   sia multilinea con due punti ("School: conjuration\\nSpell Level: ...").

Il gist ha priorita' sui campi che copre; `descriptors` e `spell_resistance`
arrivano solo dalla description (assenti nel gist reale).
Nota copertura: spell_resistance e descriptors sono limitati dalle fonti
(gist senza quei campi; colon-format quasi senza quelle righe).

Default: solo report. Con --write aggiunge `mechanics` alle entry.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.enrich_reference import normalize_name, save_json

ROOT = Path(__file__).resolve().parents[1]
SPELLS_PATH = ROOT / "data" / "reference" / "ogl" / "spells.json"
CACHE_DIR = ROOT / ".cache" / "enrichment"
GIST_GLOB = "*PathfinderSpellsJSON*"

# Chiavi di header nelle description; quelle multi-parola prima delle singole.
# Effect/Area/Targets/Source/Description/Italiano servono solo da delimitatori.
_HEADER_KEYS = [
    "Casting Time", "Saving Throw", "Spell Resistance", "Spell Level",
    "School", "Level", "Components", "Range", "Duration",
    "Effect", "Area", "Targets", "Source", "Description", "Italiano",
]
_KEY_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(_HEADER_KEYS) + r")(?![A-Za-z])\s*:?\s*"
)

_SIMPLE_FIELDS = {
    "Casting Time": "casting_time",
    "Components": "components",
    "Range": "range",
    "Duration": "duration",
    "Saving Throw": "saving_throw",
    "Spell Resistance": "spell_resistance",
}


# Marcatore di inizio prosa libera: in entrambi i formati tutte le chiavi
# header precedono "Description:", che non e' mai un campo mechanics.
_PROSE_START_RE = re.compile(r"\bDescription\s*:")


def _split_header_fields(description: str) -> dict:
    """Spezza l'header della description in coppie chiave -> valore.

    Tronca al primo "Description:" PRIMA del regex: senza questo, _KEY_RE
    matcha le chiavi header anche dentro la prosa (hazard Banishment, dove
    "Spell Resistance" in prosa finiva in `spell_resistance`).
    """
    prose = _PROSE_START_RE.search(description)
    if prose:
        description = description[:prose.start()]
    matches = list(_KEY_RE.finditer(description))
    fields = {}
    for i, m in enumerate(matches):
        key = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
        value = description[start:end].strip()
        value = re.sub(r"[;.\s]+$", "", value)
        if value and key not in fields:
            fields[key] = value
    return fields


def parse_spell_level(text: str) -> dict:
    """'cleric 3, paladin 2, sorcerer/wizard 3' -> {'cleric': 3, ...}."""
    out = {}
    for part in text.split(","):
        m = re.match(r"^\s*(.+?)\s+(\d+)\s*$", part)
        if m:
            out[m.group(1).strip().lower()] = int(m.group(2))
    return out


def parse_description_mechanics(description: str) -> dict:
    """Estrae le mechanics dall'header testuale di una description."""
    fields = _split_header_fields(description or "")
    mech = {}

    school_raw = fields.get("School")
    if school_raw:
        m = re.match(r"^([A-Za-z]+)(?:\s*\(([^)]*)\))?(?:\s*\[([^\]]*)\])?", school_raw)
        if m:
            mech["school"] = m.group(1).lower()
            descriptors = m.group(3)
            mech["descriptors"] = (
                [d.strip().lower() for d in descriptors.split(",") if d.strip()]
                if descriptors
                else []
            )

    level_raw = fields.get("Spell Level") or fields.get("Level")
    if level_raw:
        mech["spell_level"] = parse_spell_level(level_raw)

    for key, out_key in _SIMPLE_FIELDS.items():
        value = fields.get(key)
        if value:
            mech[out_key] = value

    return mech


# Prefissi locali che il gist registra in forma invertita ("X, Greater").
_INVERTIBLE_PREFIXES = ("Greater", "Lesser", "Mass")


def _gist_entry(gist: dict, name: str):
    """Cerca la entry gist per una spell locale.

    Ordine: nome esatto, poi normalizzato; se assente e il nome inizia con
    Greater/Lesser/Mass, riprova con la forma invertita "<resto>, <prefisso>"
    (es. "Greater Invisibility" -> "Invisibility, Greater").
    """
    candidates = [name]
    for prefix in _INVERTIBLE_PREFIXES:
        if name.startswith(prefix + " "):
            candidates.append(f"{name[len(prefix) + 1:]}, {prefix}")
            break
    exact = getattr(gist, "exact", None)
    if exact:
        for cand in candidates:
            if cand in exact:
                return exact[cand]
    for cand in candidates:
        entry = gist.get(cand) or gist.get(cand.lower()) or gist.get(normalize_name(cand))
        if entry:
            return entry
    return None


def merge_mechanics(entry: dict, gist: dict) -> dict:
    """Fonde regex su description (base) e campi gist (priorita')."""
    mech = parse_description_mechanics(entry.get("description") or "")
    g = _gist_entry(gist, entry.get("name", "")) if gist else None
    if not g:
        return mech

    for key in ("school", "casting_time", "components", "range", "duration",
                "saving_throw", "spell_resistance", "descriptors"):
        value = g.get(key)
        if value is not None and value != "":
            mech[key] = value.strip() if isinstance(value, str) else value

    spell_level = g.get("spell_level")
    if isinstance(spell_level, dict) and spell_level:
        mech["spell_level"] = spell_level
    elif isinstance(spell_level, str) and spell_level.strip():
        parsed = parse_spell_level(spell_level)
        if parsed:
            mech["spell_level"] = parsed

    return mech


class GistLookup(dict):
    """{nome normalizzato: entry} con mappa accessoria `.exact` {nome esatto: entry}.

    Il match esatto ha priorita' su quello normalizzato per evitare collisioni:
    il gist contiene sia "Peacebond" sia "Peace Bond", che normalizzati
    collidono (last-wins); con `.exact` ogni nome locale trova la sua entry.
    """

    def __init__(self):
        super().__init__()
        self.exact = {}


def load_gist_cache(cache_dir: Path) -> GistLookup:
    """Carica la cache gist in una GistLookup; vuota se la cache e' assente."""
    matches = sorted(cache_dir.glob(GIST_GLOB)) if cache_dir.is_dir() else []
    lookup = GistLookup()
    if not matches:
        return lookup
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    for item in data:
        name = item.get("name")
        if not name:
            continue
        lookup.exact.setdefault(name, item)
        lookup[normalize_name(name)] = item
    return lookup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="scrive `mechanics` in spells.json (default: solo report)")
    parser.add_argument("--spells", type=Path, default=SPELLS_PATH,
                        help="path del catalogo spells.json")
    args = parser.parse_args(argv)

    data = json.loads(args.spells.read_text(encoding="utf-8"))
    entries = data.get("entries", [])

    gist = load_gist_cache(CACHE_DIR)
    if gist:
        print(f"Gist cache: {len(gist)} spell caricate")
    else:
        print("Gist cache assente: solo regex su description")

    matched = []
    unmatched = []
    n_school = 0
    field_counts = Counter()
    for entry in entries:
        mech = merge_mechanics(entry, gist)
        if mech:
            matched.append(entry.get("name", "?"))
            if "school" in mech:
                n_school += 1
            field_counts.update(mech.keys())
            if args.write:
                entry["mechanics"] = mech
        else:
            unmatched.append(entry.get("name", "?"))

    print(f"mechanics: {len(matched)}/{len(entries)} entry "
          f"(di cui {n_school} con school), unmatched: {len(unmatched)}")
    print("copertura per campo:")
    for field in ("school", "descriptors", "spell_level", "casting_time",
                  "components", "range", "duration", "saving_throw",
                  "spell_resistance"):
        print(f"  {field}: {field_counts.get(field, 0)}/{len(entries)}")
    if unmatched:
        sample = ", ".join(unmatched[:20])
        print(f"unmatched sample: {sample}" + (" ..." if len(unmatched) > 20 else ""))

    if args.write:
        save_json(args.spells, data)
        print(f"Scritto: {args.spells}")
    else:
        print("Modalita' report: nessuna modifica (usa --write per scrivere)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
