#!/usr/bin/env python3
"""Riconciliazione degli incantesimi a TRE fonti (slice D5) — mai merge
silenzioso.

Legge le tre fonti e scrive UN JSON committato in `pathmaster-dd/
packages/rules-engine-v2/src/data/`: spell-sources.json — indice per nome
canonico -> {taverna?, pcgen?, pb?} con i livelli per classe di OGNI fonte
SEPARATI, piu' il report di riconciliazione (conteggi, duplicati,
divergenze di livello per classe classificate).

Fonti e policy (scritta in docs/superpowers/pcgen-import.md):

- **Taverna** `data/reference/ogl/spells.json` (2.820 entry OGL, tutti i
  libri AoN): AMPIEZZA. E' la fonte OPERATIVA del motore (`spellLevelFor`
  in catalogs/taverna-spell-data.ts) e RESTA TALE: questa slice non cambia
  nessun livello usato dal derivato (ENGINE_VERSION non si tocca).
  Livelli da mechanics.spell_level, chiavi combinate ("sorcerer/wizard")
  splittate su "/" — stessa disciplina del loader TS.
- **PCGen** `pcgen-spells.json` (1.740 entry / 1.720 nomi, import A1):
  STRUTTURA (mappa classe->livello tipizzata). 20 nomi compaiono in due
  libri con classi COMPLEMENTARI (Summon Monster/Nature's Ally I-IX,
  Repulsion, Share Language (Communal)): fusi a UNIONE di classi,
  dichiarato in report.pcgenInternalDuplicates; un conflitto di livello
  sulla stessa classe sarebbe segnalato (oggi zero).
- **Pathbuilder** `pathbuilder-spells.json` (2.922 entry, import D5):
  COPERTURA (quali classi hanno la spell in lista, incluse arcanist/
  hunter/warpriest assenti dagli altri cataloghi).

Normalizzazione nomi ESPLICITA (scritta in `normalization` del JSON):

1. NFKD, strip dei combining marks, casefold, apostrofo tipografico ->
   dritto, collasso degli spazi.
2. Forma invertita: Taverna/PB scrivono "Dispel Magic, Greater", PCGen
   "Dispel Magic (Greater)". La chiave canonica e' la forma con parentesi;
   l'inversione si applica SOLO ai qualificatori DICHIARATI (QUALIFIERS).
   Le parentesi PCGen NON di qualificatore ("Align Weapon (Chaos Only)",
   "Burning Hands (Acid)", "Bottled Ooze (1)") sono VARIANTI separate:
   mai fuse (dichiarato).

Alias di classe DICHIARATI (CLASS_ALIASES): 'magusum' -> 'magus'
(suffisso-libro UM da scrape d20pfsrd, presente in Taverna E PB),
'summoner (unchained)' -> 'unchained summoner' (doppia grafia PB).
Gli id classe sono lowercased ovunque; PCGen 'Psychic Detective' (un
archetipo nel dato, non una classe base) resta com'e': copertura non
confrontabile, dichiarato.

Divergenze di livello per classe: dove >=2 fonti coprono la stessa
spell+classe con livelli diversi, la divergenza e' REGISTRATA (spell,
classe, livelli per fonte) con una CLASSIFICAZIONE:

- `pcgen-outlier`        — Taverna e PB concordi, PCGen difforme;
- `taverna-pb-divergence`— Taverna e PB difformi (PCGen assente o concorde);
- `raw-homonym`          — omonimia RAW reale: due spell DIVERSE con lo
                           stesso nome (Fool's Gold AA vs VC);
- `declared-unresolved`  — ogni altro caso: dichiarato, MAI risolto a
                           tentativi.

I VERDICT (DIVERGENCE_VERDICTS) sono una tabella dichiarata di verifiche
su Archives of Nethys (2026-08-07, URL per spell): dicono cosa e' il RAW,
ma NON cambiano alcun dato — la divergenza resta visibile nel report come
dato, non come errore corretto. Regola del piano: "divergenza =
documentata, mai risolta a tentativi".

Uso:
  python tools/build_spell_sources.py                # scrive il JSON
  python tools/build_spell_sources.py --report-only  # solo stdout
  --taverna/--pcgen/--pb PATH  (default: posizioni note dei tre JSON)
  --out-dir PATH (default <pathmaster>/packages/rules-engine-v2/src/data)
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PATHMASTER_DATA = (
    REPO_ROOT.parent / "pathmaster-dd" / "packages/rules-engine-v2/src/data"
)
DEFAULT_TAVERNA = REPO_ROOT / "data/reference/ogl/spells.json"
DEFAULT_PCGEN = PATHMASTER_DATA / "pcgen-spells.json"
DEFAULT_PB = PATHMASTER_DATA / "pathbuilder-spells.json"

# Qualificatori DICHIARATI per la forma invertita "Base, Qual" <-> "Base
# (Qual)". Ricavati da ispezione dei suffissi reali dopo virgola nei
# dataset Taverna/PB (2026-08-07: greater 199, mass 117, communal 53,
# lesser 46, major 4 — 'major' NON compare come prefisso PCGen: le 4 voci
# ', major' collimano gia' senza inversione; incluso comunque per simmetria
# dichiarata? NO: solo i qualificatori con riscontro reale in entrambe le
# forme. Vedi tests).
QUALIFIERS = (
    "greater communal",  # prima il piu' lungo: rpartition sul suffisso
    "greater",
    "lesser",
    "mass",
    "communal",
    "improved",
    "supreme",
    "giant",
)

# Alias di classe DICHIARATI (vedi import_pathbuilder_spells.py).
CLASS_ALIASES = {
    "magusum": "magus",
    "summoner (unchained)": "unchained summoner",
}

# Verdetti DICHIARATI sulle divergenze note, da verifica su Archives of
# Nethys (2026-08-07). DICHIARAZIONE, non correzione: i dati delle fonti
# restano com'e' e la fonte operativa (Taverna) non cambia.
#
# CORREZIONI CURATE GIA' APPLICATE (la divergenza si e' CHIUSA col dato
# corretto alla fonte, con nota di correzione nel dato stesso — non un
# merge silenzioso):
# - 2026-08-08 ("overwhelming presence", "psychic"): Taverna 4 -> 9
#   (RAW AoN verificato 2026-08-07, https://aonprd.com/SpellDisplay.aspx?
#   ItemName=Overwhelming%20Presence; PB concorde). Nota di correzione in
#   data/reference/ogl/spells.json; registro in INTERPRETATIONS.md di
#   rules-engine-v2 (sezione D5). spellLevelFor cambia di conseguenza:
#   impatto derivato verificato NULLO (nessuna build corpus dichiara la
#   spell); ENGINE_VERSION "16" (stesso bump delle tabelle slot Fase A).
DIVERGENCE_VERDICTS: dict[tuple[str, str], dict] = {
    ("commune with nature", "druid"): {
        "raw": "druid 5 (ranger 4, hunter 4, psychic 5, shaman 5)",
        "assessment": "Taverna e PB concordi col RAW; il valore PCGen (4) "
        "e' difforme (probabile errore del dato PCGen).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Commune%20with%20Nature",
    },
    ("geas (lesser)", "bard"): {
        "raw": "bard 3 (sorcerer/wizard 4, witch 4, inquisitor 4, "
        "mesmerist 3, psychic 4, skald 3, arcanist 4)",
        "assessment": "Taverna e PB concordi col RAW; il valore PCGen (4) "
        "e' difforme (probabile errore del dato PCGen).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Geas,%20Lesser",
    },
    ("nondetection", "ranger"): {
        "raw": "ranger 4 (quasi tutte le altre classi 3; medium 2, hunter 4)",
        "assessment": "Taverna e PB concordi col RAW; il valore PCGen (3) "
        "e' difforme (probabile errore del dato PCGen).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Nondetection",
    },
    ("withdraw affliction", "spiritualist"): {
        "raw": "spiritualist 5 (psychic 6, shaman 6, witch 7)",
        "assessment": "Taverna e PB concordi col RAW; il valore PCGen (6) "
        "e' difforme (probabile errore del dato PCGen).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Withdraw%20Affliction",
    },
    ("fool's gold", "sorcerer"): {
        "raw": "due spell OMONIME distinte: Fool's Gold (Villain Codex, "
        "illusione, sorcerer/wizard 1) e Fool's Gold (Arcane "
        "Anthology, trasmutazione, sorcerer/wizard 2)",
        "assessment": "Taverna fonta la versione VC (illusion, 1), PB la "
        "versione AA (transmutation, 2): non un errore, "
        "un'omonimia RAW reale — classificata raw-homonym.",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Fool%27s%20Gold%20(VC)",
    },
    ("fool's gold", "wizard"): {
        "raw": "come sorcerer (omonimia VC livello 1 vs AA livello 2)",
        "assessment": "Taverna fonta la versione VC (illusion, 1), PB la "
        "versione AA (transmutation, 2): omonimia RAW reale.",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Fool%27s%20Gold%20(VC)",
    },
    ("soul transfer", "sorcerer"): {
        "raw": "sorcerer/wizard 7 (witch 7, cleric/oracle 7, psychic 7, "
        "shaman 7, spiritualist 6)",
        "assessment": "Taverna concorde col RAW; il valore PB (8) e' "
        "difforme (probabile confusione con Trap the Soul, "
        "livello 8, stessa pagina AoN).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Soul%20Transfer",
    },
    ("soul transfer", "wizard"): {
        "raw": "sorcerer/wizard 7",
        "assessment": "Taverna concorde col RAW; il valore PB (8) e' "
        "difforme (vedi sorcerer).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Soul%20Transfer",
    },
    ("soul transfer", "witch"): {
        "raw": "witch 7",
        "assessment": "Taverna concorde col RAW; il valore PB (8) e' "
        "difforme (vedi sorcerer).",
        "source": "https://aonprd.com/SpellDisplay.aspx?ItemName=Soul%20Transfer",
    },
}


def norm_name(name: str) -> str:
    """NFKD + strip combining + casefold + apostrofo dritto + spazi collassati."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.replace("’", "'").casefold().split())


def canon_key(name: str) -> str:
    """Chiave canonica: "Base, Qual" (qualificatore dichiarato) -> "base (qual)"."""
    key = norm_name(name)
    if "," in key:
        base, _, qualifier = key.rpartition(",")
        qualifier = qualifier.strip()
        if qualifier in QUALIFIERS:
            return f"{base.strip()} ({qualifier})"
    return key


def class_id(raw: str) -> str:
    cid = " ".join(raw.strip().casefold().split())
    return CLASS_ALIASES.get(cid, cid)


def load_taverna(path: Path) -> dict[str, dict]:
    """Taverna OGL: livelli da mechanics.spell_level (combinate splittate)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for entry in data.get("entries", []):
        name = entry.get("name")
        if not name:
            continue
        levels: dict[str, int] = {}
        raw_levels = (entry.get("mechanics") or {}).get("spell_level") or {}
        for key, value in raw_levels.items():
            if not isinstance(value, (int, float)):
                continue
            for cls in str(key).split("/"):
                cid = class_id(cls)
                if cid and cid not in levels:
                    levels[cid] = int(value)
        out[canon_key(name)] = {
            "name": str(name),
            "levels": levels,
            "school": (entry.get("mechanics") or {}).get("school"),
            "source": entry.get("source"),
        }
    return out


def load_pcgen(path: Path) -> tuple[dict[str, dict], dict]:
    """PCGen: 20 nomi in due libri, classi complementari -> unione dichiarata."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    merged: set[str] = set()
    conflicts = []
    for entry in data.get("entries", []):
        name = entry.get("name")
        if not name:
            continue
        key = canon_key(name)
        target = out.setdefault(
            key,
            {
                "name": str(name),
                "levels": {},
                "school": entry.get("school"),
                "source": entry.get("source_book"),
                "books": [],
            },
        )
        target["books"].append(entry.get("source_book"))
        if len(target["books"]) > 1:
            merged.add(key)
        for cls, value in (entry.get("classes") or {}).items():
            cid = class_id(cls)
            if cid in target["levels"] and target["levels"][cid] != value:
                # mai risolto a tentativi: segnalato, vince la PRIMA occorrenza
                conflicts.append(
                    {
                        "spell": key,
                        "class": cid,
                        "keptLevel": target["levels"][cid],
                        "discardedLevel": value,
                        "book": entry.get("source_book"),
                    }
                )
            else:
                target["levels"].setdefault(cid, value)
    return out, {
        "mergedNames": sorted(merged),
        "conflicts": conflicts,
        "note": "Nomi PCGen presenti in due libri della slice: fusi a "
        "UNIONE di classi (le classi sono complementari). Un "
        "conflitto di livello sulla stessa classe sarebbe "
        "segnalato in conflicts (vince la prima occorrenza, "
        "dichiarato) — oggi zero.",
    }


def load_pb(path: Path) -> dict[str, dict]:
    """Pathbuilder (import D5): livelli gia' parsati da spellLevelsDisplay."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for entry in data.get("spells", []):
        name = entry.get("name")
        if not name:
            continue
        out[canon_key(name)] = {
            "name": str(name),
            "levels": {
                class_id(c): v for c, v in (entry.get("spellLevels") or {}).items()
            },
            "school": entry.get("school"),
            "source": entry.get("source"),
        }
    return out


def _classify(levels: dict[str, int]) -> str | None:
    """Classificazione della divergenza (forma delle fonti, mai il valore)."""
    tav, pcg, pb = levels.get("taverna"), levels.get("pcgen"), levels.get("pb")
    if tav is not None and pcg is not None and pb is not None:
        if tav == pb != pcg:
            return "pcgen-outlier"
        if tav == pcg != pb:
            return "taverna-pb-divergence"
        if pb == pcg != tav:
            return "taverna-pcgen-divergence"
        return "declared-unresolved"  # tre valori diversi
    if tav is not None and pb is not None:
        return "taverna-pb-divergence"
    if tav is not None and pcg is not None:
        return "taverna-pcgen-divergence"
    if pcg is not None and pb is not None:
        return "pcgen-pb-divergence"
    return None


# Omonimie RAW DICHIARATE: due spell diverse con lo stesso nome nelle
# fonti (Fool's Gold: Villain Codex illusione 1 vs Arcane Anthology
# trasmutazione 2 — verificato AoN 2026-08-07, vedi DIVERGENCE_VERDICTS).
RAW_HOMONYMS = {"fool's gold"}


def _divergences(spells: dict[str, dict]) -> list[dict]:
    out = []
    for key in sorted(spells):
        sources = spells[key]["sources"]
        classes: set[str] = set()
        for src in sources.values():
            classes.update(src["levels"])
        for cls in sorted(classes):
            levels = {
                name: src["levels"][cls]
                for name, src in sources.items()
                if cls in src["levels"]
            }
            if len(levels) < 2 or len(set(levels.values())) == 1:
                continue
            if key in RAW_HOMONYMS:
                classification = "raw-homonym"
            else:
                classification = _classify(levels) or "declared-unresolved"
            verdict = DIVERGENCE_VERDICTS.get((key, cls))
            if verdict is None and classification != "raw-homonym":
                classification = "declared-unresolved"
            out.append(
                {
                    "spell": key,
                    "displayName": spells[key]["displayName"],
                    "class": cls,
                    "levels": levels,
                    "classification": classification,
                    "verdict": verdict,
                }
            )
    return out


def build(taverna_path: Path, pcgen_path: Path, pb_path: Path) -> dict:
    tav = load_taverna(taverna_path)
    pcg, dup_report = load_pcgen(pcgen_path)
    pb = load_pb(pb_path)

    spells: dict[str, dict] = {}
    # priorita' displayName: Taverna (ampiezza) > PCGen > PB — dichiarata
    for source_name, data in (("taverna", tav), ("pcgen", pcg), ("pb", pb)):
        for key, entry in data.items():
            slot = spells.setdefault(key, {"displayName": entry["name"], "sources": {}})
            slot["sources"][source_name] = {
                "name": entry["name"],
                "levels": entry["levels"],
                "school": entry.get("school"),
                "source": entry.get("source"),
            }

    t_keys, p_keys, b_keys = set(tav), set(pcg), set(pb)
    all_keys = t_keys | p_keys | b_keys
    counts = {
        "taverna": len(tav),
        "pcgen": len(pcg),
        "pb": len(pb),
        "union": len(all_keys),
        "intersection": {
            "tavernaPcgen": len(t_keys & p_keys),
            "tavernaPb": len(t_keys & b_keys),
            "pcgenPb": len(p_keys & b_keys),
            "allThree": len(t_keys & p_keys & b_keys),
        },
        "only": {
            "taverna": len(t_keys - p_keys - b_keys),
            "pcgen": len(p_keys - t_keys - b_keys),
            "pb": len(b_keys - t_keys - p_keys),
        },
    }

    divergences = _divergences(spells)
    classification_counts: dict[str, int] = {}
    for d in divergences:
        classification_counts[d["classification"]] = (
            classification_counts.get(d["classification"], 0) + 1
        )

    return {
        "_provenance": {
            "sources": {
                "taverna": "Master-DD-Taverna/data/reference/ogl/spells.json "
                "(2.820 entry OGL) — AMPIEZZA, fonte OPERATIVA del "
                "motore (spellLevelFor). Correzione curata Fase A "
                "2026-08-08: Overwhelming Presence psychic 4->9 "
                "(vedi commento CORREZIONI CURATE nel builder)",
                "pcgen": "pcgen-spells.json (import A1, 1.740 entry) — STRUTTURA",
                "pathbuilder": "pathbuilder-spells.json (import D5, 2.922 entry) "
                "— COPERTURA per classe",
            },
            "generated_by": "Master-DD-Taverna/tools/build_spell_sources.py",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "license": "Meccaniche e nomi: OGL 1.0a (Taverna OGL, PCGen data "
            "sets, Pathbuilder raw). Nessun testo di regole "
            "esportato (mai description).",
            "operative_source": "Il motore continua a usare spellLevelFor "
            "Taverna (catalogs/taverna-spell-data.ts) come "
            "UNICA fonte operativa dei livelli per il "
            "derivato: NESSUN cambio silenzioso — le uniche "
            "modifiche ai livelli operativi sono le "
            "correzioni curate dichiarate (vedi CORREZIONI "
            "CURATE nel builder; ENGINE_VERSION bump "
            "documentato in INTERPRETATIONS.md).",
            "conflict_policy": "Mai merge silenzioso: i livelli di ogni fonte "
            "restano SEPARATI per spell; le divergenze di "
            "livello per classe sono registrate e "
            "classificate in report.divergences, MAI "
            "risolte a tentativi. Verdetti RAW (AoN) "
            "dichiarati come DATO, non come correzione.",
        },
        "normalization": {
            "nameKey": "NFKD + strip combining + casefold + apostrofo "
            "tipografico->dritto + collasso spazi",
            "invertedForms": "'Base, Qual' (Taverna/PB) <-> 'Base (Qual)' "
            "(PCGen), solo per i qualificatori dichiarati; "
            "le parentesi NON di qualificatore restano "
            "varianti separate, mai fuse",
            "qualifiers": list(QUALIFIERS),
            "classAliases": dict(CLASS_ALIASES),
        },
        "counts": counts,
        "report": {
            "pcgenInternalDuplicates": dup_report,
            "divergences": divergences,
            "divergenceCounts": classification_counts,
        },
        "spells": spells,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--taverna", default=str(DEFAULT_TAVERNA))
    ap.add_argument("--pcgen", default=str(DEFAULT_PCGEN))
    ap.add_argument("--pb", default=str(DEFAULT_PB))
    ap.add_argument("--out-dir", default=str(PATHMASTER_DATA))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    index = build(Path(args.taverna), Path(args.pcgen), Path(args.pb))
    counts = index["counts"]
    div_counts = index["report"]["divergenceCounts"]
    print(
        f"fonti: Taverna {counts['taverna']}, PCGen {counts['pcgen']}, "
        f"PB {counts['pb']} -> unione {counts['union']}"
    )
    print(
        f"intersezioni: T&P {counts['intersection']['tavernaPcgen']}, "
        f"T&B {counts['intersection']['tavernaPb']}, "
        f"P&B {counts['intersection']['pcgenPb']}, "
        f"tutte e 3: {counts['intersection']['allThree']}"
    )
    print(
        f"solo una fonte: Taverna {counts['only']['taverna']}, "
        f"PCGen {counts['only']['pcgen']}, PB {counts['only']['pb']}"
    )
    print(
        f"duplicati interni PCGen fusi: "
        f"{len(index['report']['pcgenInternalDuplicates']['mergedNames'])} "
        f"(conflitti: "
        f"{len(index['report']['pcgenInternalDuplicates']['conflicts'])})"
    )
    print(
        f"divergenze di livello per classe: "
        f"{len(index['report']['divergences'])} {div_counts}"
    )

    if not args.report_only:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "spell-sources.json"
        path.write_text(
            json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"scritto {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
