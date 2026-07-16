#!/usr/bin/env python3
"""Sanitizza Product Identity note dai cataloghi OGC.

Applica sostituzioni testuali conservative sui campi di contenuto e sui
riferimenti fonte dei cataloghi in data/reference/ogl/. I campi tecnici
(_license, _source) non vengono toccati.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OGL_DIR = REPO_ROOT / "data" / "reference" / "ogl"

# Sostituzioni PI -> testo neutro. Ordinate per priorità (frasi prima delle parole).
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


def _replace_in_text(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    return text


def _sanitize(obj, is_root: bool = True):
    if isinstance(obj, str):
        return _replace_in_text(obj)
    if isinstance(obj, list):
        return [_sanitize(item, is_root=False) for item in obj]
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # Non toccare gli header legali
            if is_root and key in ("_license", "_source"):
                result[key] = value
            else:
                result[key] = _sanitize(value, is_root=False)
        return result
    return obj


def main() -> int:
    changed_files = 0
    for path in sorted(OGL_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sanitized = _sanitize(data, is_root=True)
        if sanitized != data:
            path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
            changed_files += 1
            print(f"Sanitizzato: {path.name}")
    print(f"File modificati: {changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
