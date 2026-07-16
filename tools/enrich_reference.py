#!/usr/bin/env python3
"""Arricchisce il catalogo reference PF1e con descrizioni complete.

Fonti supportate:
  - d20pfsrd.com (HTML, OGL) — fonte primaria per qualsiasi entry
  - PFRPG_Feat_card JSON (GitHub) — fallback per i talenti
  - Pathfinder Spells Gist (GitHub) — fallback per gli incantesimi
  - seed manuale integrato — per le entry iconiche più richieste

Uso tipico:
    python tools/enrich_reference.py --dry-run
    python tools/enrich_reference.py --limit 50
    python tools/enrich_reference.py --kind feats --source json
    python tools/enrich_reference.py --force  # sovrascrive anche entry già descritte

Requisiti:
    pip install httpx beautifulsoup4  (oltre a requirements.txt base)

Note legali:
    I dati derivati da SRD/PRD/d20pfsrd sono Open Game Content (OGL 1.0a).
    Product Identity (lore, nomi propri, marchi) viene esclusa.
    Vedi LICENSE e NOTICE nella root del repository.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

REFERENCE_DIR = ROOT_DIR / "data" / "reference"
CACHE_DIR = ROOT_DIR / ".cache" / "enrichment"

# ---------------------------------------------------------------------------
# Seed manuale per entry iconiche (contenuto OGL, da PRD/SRD).
# ---------------------------------------------------------------------------
MANUAL_SEED: dict[str, dict[str, str]] = {
    "feats": {
        "Power Attack": (
            "Italiano: Power Attack è un talento di combattimento che permette di "
            "accettare una penalità di -1 ai tiri per colpire in mischia per ottenere "
            "un bonus di +2 ai danni in mischia. Con armi a due mani il bonus aumenta "
            "del 50%, con armi secondarie viene dimezzato. Ogni +4 di BAB aumenta "
            "penalità e bonus di 1 e 2 rispettivamente. "
            "Benefit: You can choose to take a –1 penalty on all melee attack rolls "
            "and combat maneuver checks to gain a +2 bonus on all melee damage rolls. "
            "This bonus to damage is increased by half (+50%) if you are making an "
            "attack with a two-handed weapon, a one-handed weapon using two hands, or "
            "a primary natural weapon that adds 1-1/2 times your Strength modifier on "
            "damage rolls. This bonus to damage is halved (–50%) if you are making an "
            "attack with an off-hand weapon or secondary natural weapon. "
            "When your base attack bonus reaches +4, and every 4 points thereafter, "
            "the penalty increases by –1 and the bonus to damage increases by +2. "
            "You must choose to use this feat before making an attack roll, and its "
            "effects last until your next turn. The bonus damage does not apply to touch "
            "attacks or effects that do not deal hit point damage. "
            "Normal: If you wield a second weapon in your off hand, you can't use this feat."
        ),
        "Cleave": (
            "Italiano: Cleave permette, con un'azione standard, di colpire un nemico "
            "in mischia e, se il colpo va a segno, effettuare un attacco aggiuntivo "
            "contro un altro nemico a portata usando il BAB pieno. Si subisce penalità "
            "-2 alla CA fino al prossimo turno. "
            "Benefit: As a standard action, make a single melee attack against a foe "
            "within reach. If you hit, you deal damage normally and can make an "
            "additional melee attack (using your full base attack bonus) against a foe "
            "that is within reach. You can make only one additional attack per round "
            "with this feat. When you use this feat, you take a –2 penalty to your Armor "
            "Class until your next turn. "
            "Normal: Without this feat, you can only make a single melee attack as a "
            "standard action."
        ),
        "Great Cleave": (
            "Benefit: As a standard action, make a single melee attack against a foe "
            "within reach. If you hit, you deal damage normally and can make an "
            "additional melee attack (using your full base attack bonus) against another "
            "foe within reach. You can continue to make attacks against foes adjacent to "
            "the previous foe, so long as the most recent foe was hit by this feat. If "
            "you miss, you cannot make any further attacks. You can make a total number "
            "of attacks equal to your base attack bonus. You take a –2 penalty to your "
            "Armor Class until your next turn. "
            "Normal: Without this feat, you can only make a single melee attack as a "
            "standard action."
        ),
        "Combat Expertise": (
            "Benefit: You can choose to take a –1 penalty on melee attack rolls and "
            "combat maneuver checks to gain a +1 dodge bonus to your Armor Class. When "
            "your base attack bonus reaches +4, and every +4 thereafter, the penalty "
            "increases by –1 and the dodge bonus increases by +1. You can only choose to "
            "use this feat when you declare that you are making an attack or a full-attack "
            "action with a melee weapon. The effects of this feat last until your next turn."
        ),
        "Dodge": (
            "Benefit: You gain a +1 dodge bonus to your AC. A condition that makes you "
            "lose your Dex bonus to AC also makes you lose the benefits of this feat."
        ),
        "Weapon Focus": (
            "Benefit: You gain a +1 bonus on all attack rolls you make using the selected "
            "weapon. "
            "Special: You can gain this feat multiple times. Its effects do not stack. "
            "Each time you take the feat, it applies to a new type of weapon."
        ),
        "Weapon Specialization": (
            "Benefit: You gain a +2 bonus on all damage rolls you make using the selected "
            "weapon. "
            "Special: You can gain this feat multiple times. Its effects do not stack. "
            "Each time you take the feat, it applies to a new type of weapon."
        ),
        "Point-Blank Shot": (
            "Benefit: You get a +1 bonus on attack and damage rolls with ranged weapons "
            "at ranges of up to 30 feet."
        ),
        "Precise Shot": (
            "Benefit: You can shoot or throw ranged weapons at an opponent engaged in "
            "melee without taking the standard –4 penalty on your attack roll. "
            "Normal: A character without this feat who uses a ranged weapon while "
            "threatened suffers an attack of opportunity."
        ),
        "Furious Focus": (
            "Italiano: Furious Focus elimina la penalità di Power Attack sul primo "
            "attacco in mischia di ogni turno quando si impugna un'arma a due mani o "
            "un'arma ad una mano con due mani. Gli attacchi successivi subiscono la "
            "penalità normalmente. "
            "Benefit: When you are wielding a two-handed weapon or a one-handed weapon "
            "with two hands, and using the Power Attack feat, you do not suffer Power "
            "Attack's penalty on melee attack rolls on the first attack you make each turn. "
            "You still suffer the penalty on any additional attacks, including attacks of "
            "opportunity."
        ),
    },
    "spells": {
        "Fireball": (
            "Italiano: Fireball è un incantesimo di evocazione del fuoco di 3° livello "
            "che crea un'esplosione di fiamme in un raggio di 20 piedi, infliggendo 1d6 "
            "danni da fuoco per livello del lanciatore (massimo 10d6). Tiro salvezza "
            "Riflessi per dimezzare. "
            "School evocation [fire]; Level sorcerer/wizard 3, magus 3. "
            "Casting Time 1 standard action. Components V, S, M (a tiny ball of bat "
            "guano and sulfur). Range long (400 ft. + 40 ft./level). Area 20-ft.-radius "
            "spread. Duration instantaneous. Saving Throw Reflex half; Spell Resistance yes. "
            "Description: A fireball spell generates a searing explosion of flame that "
            "detonates with a low roar and deals 1d6 points of fire damage per caster level "
            "(maximum 10d6) to every creature within the area. Unattended objects also take "
            "this damage. The explosion creates almost no pressure. You point your finger "
            "and determine the range (distance and height) at which the fireball is to burst. "
            "A glowing, pea-sized bead streaks from the pointing digit and, unless it impacts "
            "upon a material body or solid barrier prior to attaining the prescribed range, "
            "blossoms with the low roar into an explosion of flame. The fireball sets fire "
            "to combustibles and damages objects in the area. It can melt metals with low "
            "melting points, such as lead, gold, copper, silver, and bronze. If the damage "
            "caused to an interposing barrier shatters or breaks through it, the fireball may "
            "continue beyond the barrier if the area permits; otherwise it stops at the "
            "barrier just as any other spell effect does."
        ),
        "Magic Missile": (
            "School evocation [force]; Level sorcerer/wizard 1, magus 1. "
            "Casting Time 1 standard action. Components V, S. Range medium (100 ft. + "
            "10 ft./level). Targets up to five creatures, no two of which can be more than "
            "15 ft. apart. Duration instantaneous. Saving Throw none; Spell Resistance yes. "
            "Description: A missile of magical energy darts forth from your fingertip and "
            "strikes its target, dealing 1d4+1 points of force damage. The missile strikes "
            "unerringly, even if the target is in melee combat, so long as it has less than "
            "total cover or total concealment. Specific parts of a creature can't be singled "
            "out. Inanimate objects are not damaged by the spell. For every two caster levels "
            "beyond 1st, you gain an additional missile—two at 3rd level, three at 5th, four "
            "at 7th, and the maximum of five missiles at 9th level or higher. If you shoot "
            "multiple missiles, you can have them strike a single creature or several "
            "creatures. A single missile can strike only one creature. You must designate "
            "targets before you check for spell resistance or roll damage."
        ),
        "Lightning Bolt": (
            "School evocation [electricity]; Level sorcerer/wizard 3, magus 3. "
            "Casting Time 1 standard action. Components V, S, M (a bit of fur and a piece "
            "of amber, glass, or a crystal rod). Range 120 ft. Area 120-ft. line. Duration "
            "instantaneous. Saving Throw Reflex half; Spell Resistance yes. "
            "Description: You release a powerful stroke of electrical energy that deals "
            "1d6 points of electricity damage per caster level (maximum 10d6) to each "
            "creature within its area. The bolt begins at your fingertips. The lightning bolt "
            "sets fire to combustibles and damages objects in its path. It can melt metals "
            "with a low melting point, such as lead, gold, copper, silver, or bronze. If the "
            "damage caused to an interposing barrier shatters or breaks through it, the bolt "
            "may continue beyond the barrier if the spell's range permits; otherwise, it "
            "stops at the barrier just as any other spell effect does."
        ),
        "Acid Arrow": (
            "School conjuration (creation) [acid]; Level sorcerer/wizard 2, magus 2. "
            "Casting Time 1 standard action. Components V, S, M (rhubarb leaf and an "
            "adder's stomach), F (a dart). Range long (400 ft. + 40 ft./level). Effect one "
            "arrow of acid. Duration 1 round + 1 round per three levels. Saving Throw none; "
            "Spell Resistance no. "
            "Description: An arrow of acid springs from your hand and speeds to its target. "
            "You must succeed on a ranged touch attack to hit your target. The arrow deals "
            "2d4 points of acid damage with no splash damage. For every three caster levels "
            "you possess, the acid, unless neutralized, lasts for another round (to a maximum "
            "of 6 additional rounds at 18th level), dealing another 2d4 points of damage in "
            "each round."
        ),
        "Cure Light Wounds": (
            "School conjuration (healing); Level bard 1, cleric/oracle 1, druid 1, inquisitor 1, "
            "paladin 1, ranger 1, witch 1. Casting Time 1 standard action. Components V, S. "
            "Range touch. Target creature touched. Duration instantaneous. Saving Throw "
            "Will half (harmless); see text; Spell Resistance yes (harmless); see text. "
            "Description: When laying your hand upon a living creature, you channel positive "
            "energy that cures 1d8 points of damage + 1 point per caster level (maximum +5). "
            "Since undead are powered by negative energy, this spell deals damage to them "
            "instead of curing their wounds. An undead creature can apply spell resistance, "
            "and can attempt a Will save to take half damage."
        ),
    },
    "items": {
        "Amulet of Natural Armor +1": (
            "Italiano: L'Amulet of Natural Armor +1 è un oggetto meraviglioso da indossare "
            "al collo che conferisce un bonus di miglioramento di +1 alla CA naturale. "
            "Aura faint transmutation; CL 5th; Slot neck; Price 2,000 gp; Weight —. "
            "Description: This amulet, usually crafted from bone or beast scales, toughens "
            "the wearer's body and flesh, giving him an enhancement bonus to his natural "
            "armor bonus of +1, +2, +3, +4, or +5, depending on the kind of amulet. "
            "Construction Requirements: Craft Wondrous Item, barkskin; Cost 1,000 gp (+1), "
            "4,000 gp (+2), 9,000 gp (+3), 16,000 gp (+4), 25,000 gp (+5)."
        ),
        "Belt of Giant Strength +2": (
            "Aura faint transmutation; CL 8th; Slot belt; Price 4,000 gp; Weight 1 lb. "
            "Description: This belt is a thick leather affair, often decorated with bronze. "
            "It grants the wearer an enhancement bonus to Strength of +2, +4, or +6. Treat "
            "this as a temporary ability bonus for the first 24 hours the belt is worn. "
            "Construction Requirements: Craft Wondrous Item, bull's strength; Cost 2,000 gp "
            "(+2), 8,000 gp (+4), 18,000 gp (+6)."
        ),
        "Headband of Vast Intelligence +2": (
            "Aura faint transmutation; CL 8th; Slot headband; Price 4,000 gp; Weight 1 lb. "
            "Description: This intricate gold headband is decorated with several small blue "
            "and deep purple gemstones. The headband grants the wearer an enhancement bonus "
            "to Intelligence of +2, +4, or +6. Treat this as a temporary ability bonus for the "
            "first 24 hours the headband is worn. A headband of vast intelligence has one skill "
            "associated with it per +2 bonus it grants. After being worn for 24 hours, the "
            "headband grants a number of skill ranks in those skills equal to the wearer's "
            "total Hit Dice. These ranks do not stack with the ranks a creature already "
            "possesses. "
            "Construction Requirements: Craft Wondrous Item, fox's cunning; Cost 2,000 gp "
            "(+2), 8,000 gp (+4), 18,000 gp (+6)."
        ),
    },
}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """Normalizza un nome per matching cross-sorgente."""
    n = name.lower()
    n = re.sub(r"[’'']", "", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Fonti esterne
# ---------------------------------------------------------------------------
def fetch_text(url: str, retries: int = 3, delay: float = 0.5) -> str:
    """Scarica un testo via HTTP con retry semplice."""
    import httpx

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "pathfinder-rag-enricher/1.0"})
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(delay * attempt)
    raise last_err or RuntimeError(f"Impossibile scaricare {url}")


def cache_path_for(url: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:120]
    return CACHE_DIR / f"{safe}.cache"


def fetch_cached(url: str, force_refresh: bool = False) -> str:
    cache = cache_path_for(url)
    if not force_refresh and cache.exists():
        return cache.read_text(encoding="utf-8")
    text = fetch_text(url)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def parse_feat_card(contents: list[str]) -> dict[str, str]:
    """Estrae descrizione/prerequisiti dal formato PFRPG_Feat_card."""
    description_parts: list[str] = []
    prereq_text = ""
    for line in contents:
        line = line.strip()
        if line.startswith("text |"):
            description_parts.append(line[6:].strip())
        elif line.startswith("property | prerequisites |"):
            prereq_text = line[len("property | prerequisites |") :].strip()
    return {
        "description": "\n\n".join(description_parts),
        "prerequisites_text": prereq_text,
    }


FEAT_CARD_BASE = "https://raw.githubusercontent.com/Luxura/PFRPG_Feat_card/master"
FEAT_CARD_FILES_CORE = [
    "FeatPFRPG-CORE.json",
    "FeatPFRPG-APG.json",
    "FeatPFRPG-ACG.json",
    "FeatPFRPG-ARG.json",
    "FeatPFRPG-UC.json",
    "FeatPFRPG-UM.json",
    "FeatPFRPG-Mythic.json",
    "FeatPFRPG-Occult.json",
    "FeatPFRPG-UCamp.json",
    "FeatPFRPG.json",  # aggregato generico, usato come fallback
]
FEAT_CARD_FILES_EXTENDED: list[str] = []  # eventuali file aggiuntivi futuri


def _load_one_feat_file(fname: str) -> list[dict]:
    """Carica un singolo file PFRPG_Feat_card e restituisce le entry valide."""
    url = f"{FEAT_CARD_BASE}/{fname}"
    try:
        text = fetch_cached(url)
        data = json.loads(text)
    except Exception as exc:
        print(f"  WARN: impossibile caricare {fname}: {exc}")
        return []
    if not isinstance(data, list):
        return []
    out = []
    for entry in data:
        title = entry.get("title", "")
        if not title:
            continue
        parsed = parse_feat_card(entry.get("contents", []))
        if parsed["description"]:
            out.append({"name": title, **parsed})
    return out


def build_feat_lookup(extended: bool = False, max_workers: int = 8) -> dict[str, dict[str, str]]:
    """Costruisce lookup talenti dai JSON PFRPG_Feat_card in parallelo."""
    lookup: dict[str, dict[str, str]] = {}
    files = list(FEAT_CARD_FILES_CORE)
    if extended:
        files.extend(FEAT_CARD_FILES_EXTENDED)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(_load_one_feat_file, fname): fname for fname in files}
        for future in concurrent.futures.as_completed(future_to_file):
            entries = future.result()
            for entry in entries:
                key = normalize_name(entry["name"])
                if key not in lookup or len(entry["description"]) > len(lookup[key].get("description", "")):
                    lookup[key] = entry
    return lookup


def build_spell_lookup() -> dict[str, dict[str, str]]:
    """Costruisce lookup incantesimi dal gist Pathfinder Spells."""
    url = "https://gist.githubusercontent.com/cityofwalls/0fdeb2da5d7b475968c8de88c75e77ad/raw/PathfinderSpellsJSON.txt"
    lookup: dict[str, dict[str, str]] = {}
    try:
        text = fetch_cached(url)
        data = json.loads(text)
    except Exception as exc:
        print(f"  WARN: impossibile caricare spell gist: {exc}")
        return lookup
    if not isinstance(data, list):
        return lookup
    for entry in data:
        name = entry.get("name", "")
        if not name:
            continue
        key = normalize_name(name)
        parts = [f"{k.replace('_', ' ').title()}: {v}" for k, v in entry.items() if k != "name" and v]
        description = "\n".join(parts)
        if description:
            lookup[key] = {"name": name, "description": description}
    return lookup


def scrape_d20pfsrd_description(url: str) -> str | None:
    """Estrae la descrizione/beneficio da una pagina d20pfsrd.

    Ritorna None se non trova una sezione utile.
    """
    try:
        html = fetch_cached(url)
    except Exception:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    # Rimuovi navbar/header/footer comuni
    for sel in ("header", "footer", "nav", "aside", ".sidebar", "#comments"):
        for el in soup.select(sel):
            el.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Cerca marcatori tipici delle pagine feat/spell/item
    markers = ("Benefit", "Description", "DESCRIPTION", "Effect", "ITEM", "Aura")
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            snippet = text[idx : idx + 2000]
            # Tronca a fine paragrafo
            end = snippet.find("\n\n")
            if end == -1:
                end = len(snippet)
            return snippet[:end].strip()
    # Fallback: primo paragrafo lungo
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
    return paragraphs[0] if paragraphs else None


# ---------------------------------------------------------------------------
# Enrichment core
# ---------------------------------------------------------------------------
def enrich_entry(
    entry: dict,
    kind: str,
    feat_lookup: dict,
    spell_lookup: dict,
    manual_seed: dict,
    force: bool,
    allow_scrape: bool,
) -> bool:
    """Aggiunge descrizione a una entry se possibile. Ritorna True se modificata."""
    name = entry.get("name", "")
    key = normalize_name(name)
    if not force and (entry.get("description") or entry.get("short_description")):
        return False

    # 1. seed manuale
    seed = manual_seed.get(kind, {}).get(name)
    if seed:
        entry["description"] = seed
        entry.setdefault("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        return True

    # 2. lookup JSON per feats/spells
    lookup = None
    if kind == "feats":
        lookup = feat_lookup.get(key)
    elif kind == "spells":
        lookup = spell_lookup.get(key)
    if lookup and lookup.get("description"):
        entry["description"] = lookup["description"]
        entry.setdefault("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        # Se il lookup fornisce prerequisiti testuali e la entry li ha vuoti, li riempiamo
        if kind == "feats" and lookup.get("prerequisites_text") and not entry.get("prerequisites"):
            entry["prerequisites"] = [p.strip() for p in lookup["prerequisites_text"].split(",") if p.strip()]
        return True

    # 3. scraping d20pfsrd (solo se esplicitamente abilitato)
    if allow_scrape:
        urls = entry.get("reference_urls", [])
        d20_url = next((u for u in urls if "d20pfsrd.com" in u), None)
        if d20_url:
            desc = scrape_d20pfsrd_description(d20_url)
            if desc:
                entry["description"] = desc
                entry.setdefault("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Arricchisce il catalogo reference PF1e")
    parser.add_argument(
        "--kind",
        choices=["feats", "spells", "items", "all"],
        default="all",
        help="Tipo di catalogo da arricchire",
    )
    parser.add_argument(
        "--source",
        choices=["seed", "json", "scrape", "all"],
        default="all",
        help="Fonte da usare: seed (manuale), json (dataset esterni), scrape (d20pfsrd), all",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Numero massimo di entry da arricchire per file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non scrive i file, stampa solo statistiche",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sovrascrive anche le entry che hanno già una descrizione",
    )
    parser.add_argument(
        "--no-cache-refresh",
        action="store_true",
        help="Usa la cache locale se disponibile (non riscarica le fonti JSON)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REFERENCE_DIR,
        help="Directory di output per i JSON arricchiti",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Usa anche i file PFRPG_Feat_card estesi (handbook minori)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallelismo per il download delle fonti JSON",
    )
    args = parser.parse_args()

    kinds = ["feats", "spells", "items"] if args.kind == "all" else [args.kind]
    allow_scrape = args.source in ("scrape", "all")
    use_json = args.source in ("json", "all")
    use_seed = args.source in ("seed", "all")

    # Costruisci lookup (pigro: solo se richiesto)
    feat_lookup: dict = {}
    spell_lookup: dict = {}
    if use_json and "feats" in kinds:
        print("Caricamento lookup talenti da PFRPG_Feat_card...")
        feat_lookup = build_feat_lookup(extended=args.extended, max_workers=args.max_workers)
        print(f"  talenti trovati: {len(feat_lookup)}")
    if use_json and "spells" in kinds:
        print("Caricamento lookup incantesimi da spell gist...")
        spell_lookup = build_spell_lookup()
        print(f"  incantesimi trovati: {len(spell_lookup)}")

    seed = MANUAL_SEED if use_seed else {"feats": {}, "spells": {}, "items": {}}

    stats: dict[str, dict[str, int]] = {}
    for kind in kinds:
        src_path = REFERENCE_DIR / f"{kind}.json"
        if not src_path.exists():
            print(f"SKIP: {src_path} non trovato")
            continue

        data = load_json(src_path)
        if not isinstance(data, list):
            print(f"SKIP: {src_path} non è una lista")
            continue

        enriched = 0
        examined = 0
        limit = args.limit if args.limit is not None else len(data)
        for entry in data[:limit]:
            examined += 1
            if enrich_entry(
                entry,
                kind,
                feat_lookup if use_json else {},
                spell_lookup if use_json else {},
                seed,
                args.force,
                allow_scrape,
            ):
                enriched += 1

        stats[kind] = {"examined": examined, "enriched": enriched, "total": len(data)}
        if not args.dry_run:
            out_path = args.output_dir / f"{kind}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            save_json(out_path, data)
            print(f"Scritto {out_path}: arricchite {enriched}/{examined} (totale {len(data)})")
        else:
            print(f"DRY-RUN {kind}: arricchirebbe {enriched}/{examined} (totale {len(data)})")

    # Stampa riepilogo
    print("\n=== Riepilogo ===")
    for kind, s in stats.items():
        print(f"{kind}: {s['enriched']}/{s['examined']} esaminate (catalogo {s['total']})")


if __name__ == "__main__":
    main()
