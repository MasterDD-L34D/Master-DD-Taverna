#!/usr/bin/env python3
"""Helper condivisi per l'import dei cataloghi OGL (aonprd.com 1e).

Estratti da tools/import_reference.py, che li re-esporta (facade) per
compatibilita' con i consumatori esistenti. Qui vivono solo costanti e
funzioni pure (stdlib + duck-typing sulle tabelle BeautifulSoup): niente
fetch di rete, niente filtri PI — quelli restano nei moduli di dominio.
"""
import json
import re
from pathlib import Path

OGL_DIR = Path(__file__).resolve().parents[1] / "data/reference/ogl"
LICENSE = "Open Game Content under OGL 1.0a. See LICENSE-OGL.txt and COPYRIGHT_NOTICE.txt."
SOURCE = "Pathfinder RPG Reference Document © 2011 Paizo Publishing, LLC; Archives of Nethys (aonprd.com)."

BASE = "https://aonprd.com/"


def slug(name):
    """Nome -> slug snake_case per source_id."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def source_id(source_slug, name):
    """Pattern catalogo: <slug_sorgente>:<slug_nome>."""
    return f"{source_slug}:{slug(name)}"


def clean(text):
    """Normalizza whitespace."""
    return " ".join(text.split())


def _cell_text(cell):
    """Testo normalizzato di una cella, senza i <sup> (footnote marker AoN:
    '2 lbs.<sup>1</sup>' -> '2 lbs.')."""
    for sup in cell.find_all("sup"):
        sup.decompose()
    return clean(cell.get_text())


def table_rows(table):
    """<table> -> lista di dict {header: cella} (header dal primo <tr>)."""
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [_cell_text(c) for c in rows[0].find_all(["th", "td"])]
    out = []
    for row in rows[1:]:
        cells = [_cell_text(c) for c in row.find_all(["th", "td"])]
        if len(cells) == len(headers) and any(cells):
            out.append(dict(zip(headers, cells)))
    return out


def write_catalog(path, entries, license_text=LICENSE, source_text=SOURCE):
    """Scrive il catalogo con header _license/_source (default: costanti AoN;
    i builder di merge passano gli header originali del catalogo esistente)."""
    payload = {"_license": license_text, "_source": source_text, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"scritto {path} ({len(entries)} entry)")


def _to_bonus(text):
    """'+3' -> 3, '+0' -> 0, '+6/+1' -> 6 (primo attacco), '-' -> None."""
    m = re.match(r"^\+(\d+)", text)
    return int(m.group(1)) if m else None


def _parse_level(label):
    """'1st' -> 1, '2nd' -> 2, '3rd' -> 3, '4th' -> 4."""
    m = re.match(r"(\d+)", label)
    return int(m.group(1)) if m else None


def _header_index(table):
    """(indice, headers) del <tr> con gli header di colonna della tabella di
    progressione (contiene 'Level' + 'Base Attack Bonus'). Le tabelle caster
    hanno una riga di gruppo ('Spells Per Day' con colspan) sopra gli header;
    i wrapper di layout annidano la tabella: celle dirette, non ricorsive."""
    for idx, tr in enumerate(table.find_all("tr", recursive=False)[:3]):
        headers = [clean(c.get_text()) for c in tr.find_all(["th", "td"], recursive=False)]
        if "Level" in headers and "Base Attack Bonus" in headers:
            return idx, headers
    return None, []


def _class_skill_matches(skill_name, class_skill):
    """Match skill del catalogo vs etichetta class_skills di classes.json.
    Case-insensitive; 'Knowledge (all)' matcha ogni Knowledge specifica."""
    s = skill_name.lower()
    c = class_skill.lower()
    if c == "knowledge (all)":
        return s.startswith("knowledge (")
    return s == c


def extract_prerequisites(description):
    """Estrae i prerequisiti da una description testuale (riga 'Prerequisite(s): ...').
    Ritorna lista di stringhe (split su virgola), [] se assenti."""
    m = re.search(r"Prerequisites?:\s*(.+?)(?:\.\s*(?:\n|$)|\.$)", description, re.S)
    if not m:
        return []
    raw = clean(m.group(1))
    if not raw or raw.lower() == "none":
        return []
    return [clean(p) for p in raw.split(",") if clean(p)]


def split_prereq_string(text):
    """'Str 13, base attack bonus +1' -> ['Str 13', 'base attack bonus +1'].

    Split su virgola + clean; scarta '—'/'-'/segmenti vuoti. Una virgola
    dentro parentesi NON spezza: un segmento con '(' non bilanciata e'
    concatenato al successivo finche' il buffer non torna bilanciato."""
    parts, buf = [], ""
    for seg in text.split(","):
        buf = f"{buf},{seg}" if buf else seg
        if buf.count("(") <= buf.count(")"):
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    out = []
    for p in parts:
        p = clean(p)
        # La fonte puo' chiudere la frase col punto: rimosso, stessa regola
        # di clean_existing_prerequisites.
        if p.endswith("."):
            p = p[:-1]
        if p and p not in ("—", "-"):
            out.append(p)
    return out


def clean_existing_prerequisites(entry):
    """Ripulisce i prerequisites gia' presenti in una entry feats:
    (a) scarta i segmenti autoreferenziali (uguali al nome entry,
        case-insensitive, con o senza punto finale): artefatti dell'import
        d20pfsrd per talenti che in realta' non hanno prerequisiti
        ('Improved Initiative.' su Improved Initiative, indice AoN: '—');
    (b) rimuove il punto finale dai segmenti ('base attack bonus +1.' ->
        'base attack bonus +1'), solo se ultimo carattere.
    Ritorna la lista ripulita; NON modifica la entry (ci pensa il builder)."""
    name = entry.get("name", "").lower()
    cleaned = []
    for p in entry.get("prerequisites", []):
        base = p[:-1] if p.endswith(".") else p
        if base.lower() == name:
            continue
        cleaned.append(base)
    return cleaned
