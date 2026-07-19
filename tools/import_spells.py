#!/usr/bin/env python3
"""Import del dominio spells da aonprd.com (SpellDisplay) — merge in place.

Primo dominio "parallelo-sicuro": NON si registra in import_reference.DOMAINS,
cosi' il modulo condiviso resta intoccato; il pattern (parser puro + builder
con write=False di default + PI scan fail-closed) e' lo stesso del playbook.

Forma reale delle pagine `SpellDisplay.aspx?ItemName=...` (ricognizione
2026-07-19 su Acid Arrow e Fireball, cache aon_cache):
- contenuto in <table id="MainContent_DataListTypes"> -> <td> -> <span>;
- la pagina puo' contenere PIU' blocchi separati da <h1 class="title">
  (la spell richiesta + varianti, es. "Controlled Fireball") e sezioni
  accessorie <h2 class="title"> (es. "Mythic Fireball": escluse);
- in ogni blocco: label in <b> (Source, School, Level, Casting Time,
  Components, Range, Effect/Area/Targets, Duration, Saving Throw,
  Spell Resistance) con valore in testo/link, sezioni <h3 class="framing">
  (Casting/Effect/Description) come delimitatori; la prosa segue Description
  e NON finisce nelle mechanics (fail-closed sulle label note).

Differenza chiave vs d20pfsrd: AoN elenca le classi di Level SEPARATE
("arcanist 3, sorcerer 3, wizard 3"), non combinate ("sorcerer/wizard 3").
Il merge e' conservativo: riempie SOLO i campi mechanics mancanti nella
entry del catalogo, MAI sovrascrive i valori curati; `spell_level` e'
riempito solo se del tutto assente (il merge per-chiave mescolerebbe le
due forme). Le discrepanze sono stampate nel report.

Uso:
  python tools/import_spells.py            # report (solo cache, MAI rete)
  python tools/import_spells.py --write    # scrive il merge in spells.json
  python tools/import_spells.py --fetch N  # scarica al piu' N pagine mancanti
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup, Tag

from tools.enrich_spells import _SIMPLE_FIELDS, parse_spell_level
from tools.legal_filter import _find_pi
from tools.reference_fetch import cache_path, fetch
from tools.reference_lib import BASE, LICENSE, OGL_DIR, SOURCE, clean, write_catalog

SPELLS_PATH = OGL_DIR / "spells.json"

# Label <b> riconosciute nel blocco. Effect/Area/Targets servono solo da
# delimitatori (il loro testo non entra nelle mechanics, shape esistente).
_KNOWN_LABELS = frozenset(
    ["Source", "School", "Level", "Casting Time", "Components", "Range",
     "Effect", "Area", "Targets", "Duration", "Saving Throw",
     "Spell Resistance"])

# Stessa regex di enrich_spells.parse_description_mechanics: school, poi
# subschool tra () (scartata, non prevista dallo shape), descriptors tra [].
_SCHOOL_RE = re.compile(r"^([A-Za-z]+)(?:\s*\(([^)]*)\))?(?:\s*\[([^\]]*)\])?")


def _find_spell_block(soup, name):
    """<h1 class="title"> del blocco `name` dentro la tabella AoN, o None.

    Fail-closed: se il blocco non c'e' (pagina errata/404 mascherata) si
    ritorna None — MAI il primo blocco disponibile."""
    table = soup.find("table", id="MainContent_DataListTypes")
    if table is None:
        return None
    for h1 in table.find_all("h1", class_="title"):
        if clean(h1.get_text()).lower() == name.lower():
            return h1
    return None


def _block_fields(h1):
    """Coppie label -> valore raccolte dai <b> del blocco.

    Il blocco va dall'h1.title al prossimo h1/h2.title (varianti e sezioni
    mythic escluse). Gli h3.framing chiudono il campo corrente: la prosa
    dopo "Description" non finisce in nessun campo."""
    fields = {}
    current = None
    for node in h1.next_siblings:
        if isinstance(node, Tag):
            if node.name in ("h1", "h2") and "title" in (node.get("class") or []):
                break
            if node.name == "h3":
                current = None
                continue
            if node.name == "b":
                label = clean(node.get_text())
                # Un <b> non-label (es. 'Augmented (6th)') chiude il campo:
                # la prosa in grassetto non deve accumularsi nel valore.
                current = label if label in _KNOWN_LABELS else None
                if current is not None and current not in fields:
                    fields[current] = []
                continue
        if current is not None:
            text = node.get_text() if isinstance(node, Tag) else str(node)
            fields[current].append(text)
    # Stesso strip dei separatori finali di enrich_spells._split_header_fields.
    return {k: re.sub(r"[;.\s]+$", "", clean("".join(parts)))
            for k, parts in fields.items()}


def parse_spell(html, name):
    """Pagina SpellDisplay -> entry catalogo per `name` (None se assente).

    Estrae solo name/source/mechanics: description e tags restano quelli
    curati del catalogo (il builder non li tocca)."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = _find_spell_block(soup, name)
    if h1 is None:
        return None
    fields = _block_fields(h1)

    source = None
    source_raw = fields.get("Source")
    if source_raw:
        # Primo libro = prefisso fino a 'pg. N' (criterio dei traits).
        book = re.match(r"^(.+?)\s+pg\.?\s*\d+", source_raw)
        source = clean(book.group(1)) if book else source_raw

    mech = {}
    school_raw = fields.get("School")
    if school_raw:
        m = _SCHOOL_RE.match(school_raw)
        if m:
            mech["school"] = m.group(1).lower()
            descriptors = m.group(3)
            mech["descriptors"] = ([d.strip().lower() for d in descriptors.split(",")
                                    if d.strip()] if descriptors else [])
    level_raw = fields.get("Level")
    if level_raw:
        mech["spell_level"] = parse_spell_level(level_raw)
    for key, out_key in _SIMPLE_FIELDS.items():
        value = fields.get(key)
        if value:
            mech[out_key] = value

    return {
        "name": name,
        "source": source or "PFRPG Core",
        "references": [f"AoN: {name} (Spells)"],
        "reference_urls": [BASE + f"SpellDisplay.aspx?ItemName={name.replace(' ', '%20')}"],
        "mechanics": mech,
    }


def _expand_spell_level(spell_level):
    """{classe: livello} con le chiavi combinate espanse ('sorcerer/wizard'
    -> sorcerer + wizard), per confrontare la forma d20pfsrd con quella AoN."""
    out = {}
    for classes, level in spell_level.items():
        for cls in classes.split("/"):
            out[cls.strip()] = level
    return out


def _merge_entry(entry, parsed):
    """Merge conservativo AoN -> entry catalogo. Ritorna (changed, notes).

    Riempie SOLO i campi mechanics mancanti; i valori curati non sono mai
    sovrascritti (le discrepanze finiscono in `notes`). `spell_level` e'
    copiato solo se del tutto assente: AoN separa le classi, il catalogo ha
    chiavi combinate d20pfsrd, e un merge per-chiave le duplicherebbe."""
    mech = entry.get("mechanics") or {}
    new = parsed["mechanics"]
    changed, notes = False, []
    for field in ("school", "casting_time", "components", "range", "duration",
                  "saving_throw", "spell_resistance"):
        value = new.get(field)
        if not value:
            continue
        if not mech.get(field):
            mech[field] = value
            changed = True
            notes.append(f"+{field} (da AoN)")
        elif mech[field] != value:
            notes.append(f"discrepanza {field}: catalogo={mech[field]!r} vs aon={value!r}")
    if new.get("descriptors") and not mech.get("descriptors"):
        mech["descriptors"] = new["descriptors"]
        changed = True
        notes.append("+descriptors (da AoN)")
    if new.get("spell_level"):
        if not mech.get("spell_level"):
            mech["spell_level"] = new["spell_level"]
            changed = True
            notes.append("+spell_level (da AoN)")
        elif _expand_spell_level(mech["spell_level"]) != _expand_spell_level(new["spell_level"]):
            notes.append("discrepanza spell_level: "
                         f"catalogo={mech['spell_level']} vs aon={new['spell_level']}")
    if changed:
        entry["mechanics"] = mech
    return changed, notes


def _spell_pi_hits(entry):
    """Occorrenze PI (legal_filter._find_pi) nei campi testuali che il merge
    potrebbe scrivere nel catalogo: name, source, valori stringa delle
    mechanics, descriptors e classi di spell_level."""
    mech = entry.get("mechanics", {})
    texts = [entry.get("name", ""), entry.get("source", "")]
    texts += [v for v in mech.values() if isinstance(v, str)]
    texts += list(mech.get("descriptors", []))
    texts += list(mech.get("spell_level", {}).keys())
    return [hit for text in texts for hit in _find_pi(text)]


def build_spells(write=False, max_fetch=0):
    """Merge in place su spells.json dalle pagine AoN.

    Di default lavora SOLO sulla cache su disco (MAI fetch massivo: 1035
    pagine x ~2.5s cortesia = ~45 min); con max_fetch>0 scarica al piu' N
    pagine mancanti via reference_fetch. Report matched/unmatched/non in
    cache/discrepanze; assert di copertura (school + spell_level su ogni
    pagina parsata); entry con PI residua scartate (fail-closed)."""
    with open(SPELLS_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    source_text = catalog.get("_source", SOURCE)

    matched, unmatched, uncached, skipped_pi = [], [], [], []
    changed_names, all_notes = [], []
    n_fetched = 0
    for entry in catalog["entries"]:
        url = next((u for u in entry.get("reference_urls", []) if "aonprd.com" in u), None)
        if url is None:
            unmatched.append(entry["name"])
            continue
        cached = cache_path(url).exists()
        if not cached:
            if n_fetched >= max_fetch:
                uncached.append(entry["name"])
                continue
            n_fetched += 1  # il fetch qui sotto scarica (delay cortese 2s)
        html = fetch(url)  # cache hit, oppure rete se appena contato sopra
        parsed = parse_spell(html, entry["name"])
        if parsed is None:
            unmatched.append(entry["name"])
            continue
        hits = _spell_pi_hits(parsed)
        if hits:
            terms = sorted({h["term"] for h in hits})
            skipped_pi.append((entry["name"], terms))
            continue
        # Assert di copertura sui campi chiave (pagina parsata ma vuota =
        # forma AoN cambiata: fallire forte, non fondere dati parziali).
        assert parsed["mechanics"].get("school"), f"{entry['name']}: school non parsata"
        assert parsed["mechanics"].get("spell_level"), f"{entry['name']}: spell_level non parsato"
        matched.append(entry["name"])
        changed, notes = _merge_entry(entry, parsed)
        if changed:
            changed_names.append(entry["name"])
        all_notes += [f"{entry['name']}: {n}" for n in notes]

    print(f"matched: {len(matched)}, unmatched: {len(unmatched)}, "
          f"non in cache: {len(uncached)}, scaricate ora: {n_fetched}")
    print(f"entry da aggiornare: {len(changed_names)}, PI scartate: {len(skipped_pi)}")
    if uncached and max_fetch == 0:
        seconds = len(uncached) * 2.5
        print(f"nota: {len(uncached)} pagine non in cache; per un import completo "
              f"rilancia con --fetch N (stima ~{int(seconds // 60)} min a 2.5s/pagina)")
    if all_notes:
        print("note merge:")
        for line in all_notes[:30]:
            print(f"  {line}")
        if len(all_notes) > 30:
            print(f"  ... altre {len(all_notes) - 30}")
    if skipped_pi:
        for name, terms in skipped_pi:
            print(f"nota: {name}: scartata per PI: {', '.join(terms)}")

    if not write:
        print(f"report: {len(catalog['entries'])} entry (write=False, nessuna scrittura)")
        return
    if matched and "aonprd" not in source_text:
        source_text = source_text.rstrip(".") + "; Archives of Nethys (aonprd.com)."
    if not changed_names and source_text == catalog.get("_source", SOURCE):
        print("nessun cambio reale: niente scrittura")
        return
    write_catalog(SPELLS_PATH, catalog["entries"],
                  license_text=catalog.get("_license", LICENSE), source_text=source_text)
    if skipped_pi:
        path = OGL_DIR.parents[2] / "reports" / "pi_removed_spells.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{name}: {', '.join(terms)}" for name, terms in sorted(skipped_pi)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"scritto {path} ({len(lines)} entry scartate)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="scrive il merge in spells.json (default: solo report)")
    ap.add_argument("--fetch", type=int, default=0, metavar="N",
                    help="scarica al piu' N pagine mancanti (default 0: solo cache)")
    args = ap.parse_args(argv)
    build_spells(write=args.write, max_fetch=args.fetch)


if __name__ == "__main__":
    main()
