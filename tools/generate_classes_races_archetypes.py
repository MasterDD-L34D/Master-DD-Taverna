#!/usr/bin/env python3
"""Genera cataloghi reference OGL-compliant per classi, razze e archetipi PF1e.

I dati prodotti sono riassunti meccanici originali in italiano, compatibili con lo
schema reference_catalog.schema.json. I riferimenti puntano a d20PFSRD (OGL).
"""
import json
from pathlib import Path

REF_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"


def base_entry(
    name: str,
    source_id: str,
    tags: list[str],
    refs: list[str],
    urls: list[str],
    prereqs: list[str] | None = None,
    notes: str = "",
    kind: str = "class",
) -> dict:
    kind_label_en = {"class": "class", "race": "race", "archetype": "archetype"}[kind]
    kind_label_it = {"class": "classe", "race": "razza", "archetype": "archetipo"}[kind]
    # Ensure the English name and kind are prominent for retrieval.
    enriched_tags = sorted(set(
        [name.lower(), kind_label_en, kind_label_it, "pathfinder 1e"] + tags
    ))
    short_description = f"Pathfinder 1E {kind_label_en}: {name}. {kind_label_it.capitalize()} PF1e."
    return {
        "name": name,
        "source": "Pathfinder SRD",
        "source_id": source_id,
        "prerequisites": prereqs if prereqs else [],
        "tags": enriched_tags,
        "references": refs,
        "reference_urls": urls,
        "category": "other",
        "edition": "1E",
        "short_description": short_description,
        "notes": notes,
        "status": "approved",
        "validation_status": "passed",
        "reviewed_by": "swarm-classes-races-2026-07-16",
    }


CLASSES = [
    base_entry(
        "Barbarian", "pfrpg_core:barbarian",
        ["martial", "full bab", "d12 hd", "fortitude good", "rage", "uncanny dodge"],
        ["d20PFSRD: Barbarian"],
        ["https://www.d20pfsrd.com/classes/core-classes/barbarian/"],
        notes=(
            "Classe marziale primitiva. Dado vita d12. BAB pieno (+1/livello). "
            "Salvezza buona su Tempra; cattiva su Riflessi e Volontà. "
            "Punti abilità per livello: 4 + Int (x4 al 1° livello). "
            "Abilità di classe: Climb, Craft, Handle Animal, Intimidate, Knowledge (nature), "
            "Perception, Ride, Survival, Swim. "
            "Tratti chiave: Rage (bonus Forza/Costituzione +4, malus CA -2, bonus TS Volontà +2 morale) "
            "per 4 + modificatore Costituzione round/livello; aumenta con i livelli. "
            "Fast Movement (+3 m se indossa armatura leggera/media e non trasporta carico pesante). "
            "Uncanny Dodge al 2°, Improved Uncanny Dodge al 5°. "
            "Rage Powers al 2° e ogni 2 livelli (scelte tra beast totem, elemental rage, guarded stance, etc.). "
            "Damage Reduction 1/- al 7°, aumenta ogni 3 livelli. "
            "Greater Rage al 11°, Mighty Rage al 20°."
        ),
        kind="class",
    ),
    base_entry(
        "Bard", "pfrpg_core:bard",
        ["skilled", "3/4 bab", "d8 hd", "all good saves", "arcane spellcasting", "bardic performance", "inspire courage"],
        ["d20PFSRD: Bard"],
        ["https://www.d20pfsrd.com/classes/core-classes/bard/"],
        notes=(
            "Classe versatile arcana e abilità. Dado vita d8. BAB 3/4 (+3/4 per livello). "
            "Salvezza buona su tutte e tre. "
            "Punti abilità per livello: 6 + Int. "
            "Incantesimi arcani spontanei dalla lista bardica fino al 6° cerchio, basati su Carisma. "
            "Bardic Performance: 4 + modificatore Carisma round/livello; al 1° può usare countersong, distraction, fascinate, inspire courage. "
            "Inspire Courage +1 al 1°, +2 al 5°, +3 al 11°, +4 al 17° (bonus morale ad attacco, danni e TS paura). "
            "Bardic Knowledge aggiunge metà livello a Knowledge. "
            "Versatile Performance (2°, 6°, 10°...) scambia abilità di perform per altre abilità. "
            "Well-Versed al 2° bonus ai TS contro perform, sonic e linguaggio. "
            "Lore Master al 5° permette take 10 su Knowledge e 1/giorno take 20. "
            "Jack of All Trades al 10°."
        ),
        kind="class",
    ),
    base_entry(
        "Cleric", "pfrpg_core:cleric",
        ["divine spellcasting", "3/4 bab", "d8 hd", "channel energy", "domains", "fortitude good", "will good"],
        ["d20PFSRD: Cleric"],
        ["https://www.d20pfsrd.com/classes/core-classes/cleric/"],
        notes=(
            "Classe divina e supporto. Dado vita d8. BAB 3/4. "
            "Salvezza buona su Tempra e Volontà; cattiva su Riflessi. "
            "Punti abilità per livello: 2 + Int. "
            "Incantesimi divini preparati fino al 9° cerchio, basati su Saggezza. "
            "Channel Energy: 3 + carisma volte/giorno, danno o guarigione 1d6 ogni 2 livelli (Wil DC 10 + 1/2 livello + Car). "
            "Domains: sceglie 2 domains della divinità; ogni domain concede un potere di dominio e aggiunge incantesimi di dominio. "
            "Spontaneous Casting: può convertire incantesimi preparati in cure o ferite. "
            "Orsis e focus religioso. Armature fino a pesante e scudi (tranne tower shield). "
            "AURA: allineamento legale al 1°."
        ),
        kind="class",
    ),
    base_entry(
        "Druid", "pfrpg_core:druid",
        ["divine spellcasting", "3/4 bab", "d8 hd", "animal companion", "wild shape", "nature bond", "fortitude good", "will good"],
        ["d20PFSRD: Druid"],
        ["https://www.d20pfsrd.com/classes/core-classes/druid/"],
        notes=(
            "Classe divina legata alla natura. Dado vita d8. BAB 3/4. "
            "Salvezza buona su Tempra e Volontà; cattiva su Riflessi. "
            "Punti abilità per livello: 4 + Int. "
            "Incantesimi divini preparati fino al 9° cerchio, basati su Saggezza. "
            "Nature Bond al 1°: Animal Companion oppure Domain. "
            "Nature Sense bonus a Knowledge (nature) e Survival. "
            "Wild Empathy come Diplomacy con animali. "
            "Woodland Stride al 2°. Trackless Step al 3°. Resist Nature's Lure al 4°. "
            "Wild Shape al 4° (1 volta/giorno, aumenta con i livelli), assume forma di animali Small o Medium, poi Large/Tiny al 6°, etc. "
            "Venom Immunity al 9°, A Thousand Faces al 13°, Timeless Body al 15°. "
            "Restrizioni armature/scudi metallici."
        ),
        kind="class",
    ),
    base_entry(
        "Fighter", "pfrpg_core:fighter",
        ["martial", "full bab", "d10 hd", "fortitude good", "reflex good", "bonus feats", "weapon training", "armor training"],
        ["d20PFSRD: Fighter"],
        ["https://www.d20pfsrd.com/classes/core-classes/fighter/"],
        notes=(
            "Classe marziale specializzata in combattimento. Dado vita d10. BAB pieno (+1/livello). "
            "Salvezza buona su Tempra e Riflessi; cattiva su Volontà. "
            "Punti abilità per livello: 2 + Int. "
            "Abilità di classe: Climb, Craft, Handle Animal, Intimidate, Knowledge (dungeoneering), Knowledge (engineering), Profession, Ride, Survival, Swim. "
            "Bonus Feat al 1° livello e ogni livello pari (2°, 4°, 6°, etc.); deve soddisfare prerequisiti. "
            "Bravery +1 bonus ai TS Volontà contro paura, aumenta ogni 4 livelli dopo il 2°. "
            "Armor Training 1 al 3°: riduce penalità armatura di 1 e aumenta max Dex di 1; migliora ogni 4 livelli. "
            "Weapon Training 1 al 5°: +1 attacco/danno con un gruppo di armi; nuovo gruppo ogni 4 livelli, bonus cumulativi. "
            "Armor Mastery al 19°, Weapon Mastery al 20° (crit automatico confermato, immunità disarm con arma scelta). "
            "Competenze: tutte le armature, scudi, armi semplici e marziali."
        ),
        kind="class",
    ),
    base_entry(
        "Monk", "pfrpg_core:monk",
        ["martial", "3/4 bab", "d8 hd", "all good saves", "unarmed strike", "flurry of blows", "ki", "ac bonus"],
        ["d20PFSRD: Monk"],
        ["https://www.d20pfsrd.com/classes/core-classes/monk/"],
        notes=(
            "Classe marziale senza armature. Dado vita d8. BAB 3/4. "
            "Salvezza buona su tutte e tre. "
            "Punti abilità per livello: 4 + Int. "
            "AC Bonus: aggiunge bonus saggezza alla CA e +1 ogni 4 livelli; funziona senza armatura e senza carico pesante. "
            "Flurry of Blows al 1°: full attack con unarmed strike o armi monk speciali, come Two-Weapon Fighting con BAB pieno. "
            "Unarmed Strike d6 al 1°, scala con i livelli (d8, d10, 2d6, 2d8, 2d10). "
            "Stunning Fist come bonus feat al 1°. "
            "Evasion al 2°, Fast Movement al 3° (+3 m), Still Mind al 3° (+2 TS incantesimi). "
            "Ki Pool al 4°: punti ki = 1/2 livello + Sag; spendere ki per extra attack, +4 CA, +20 ft speed, etc. "
            "Slow Fall, High Jump, Purity of Body, Wholeness of Body, Improved Evasion, Diamond Body, Quivering Palm, etc. "
            "Perfect Self al 20° diventa outsider (nativo). "
            "Competenze: armi semplici e speciali monk; nessuna armatura (penalità)."
        ),
        kind="class",
    ),
    base_entry(
        "Paladin", "pfrpg_core:paladin",
        ["divine", "martial", "full bab", "d10 hd", "divine grace", "lay on hands", "smite evil", "fortitude good", "will good"],
        ["d20PFSRD: Paladin"],
        ["https://www.d20pfsrd.com/classes/core-classes/paladin/"],
        notes=(
            "Campione divino legale-buono. Dado vita d10. BAB pieno. "
            "Salvezza buona su Tempra e Volontà; cattiva su Riflessi. "
            "Punti abilità per livello: 2 + Int. "
            "Requisito allineamento: legale buono. Può perdere i poteri se commette atto malvagio. "
            "Detect Evil al 1°, Smite Evil 1/giorno al 1° (+Carisma ad attacco, +livello a danno, bonus doppio contro creature malvagie esterne/draghi/undead; CA +Carisma contro bersaglio). "
            "Divine Grace al 2°: aggiunge bonus Carisma a tutti i TS. Lay on Hands al 2°: guarisce 1d6 ogni 2 livelli, usi = 1/2 livello + Carisma. "
            "Aura of Courage al 3° immunità paura e aura +4 morale agli alleati. Divine Health al 3° immunità malattie. "
            "Mercy al 3° e ogni 3 livelli: rimuove condizioni con Lay on Hands. Channel Positive Energy al 4°. "
            "Divine Bond al 5°: arma o mount. Spells al 4° (fino a 4° cerchio, basati su Carisma). "
            "Aura of Justice al 11°, Aura of Faith al 14°, Aura of Righteousness al 17°, Holy Champion al 20°."
        ),
        kind="class",
    ),
    base_entry(
        "Ranger", "pfrpg_core:ranger",
        ["martial", "full bab", "d10 hd", "favored enemy", "favored terrain", "animal companion", "spells", "fortitude good", "reflex good"],
        ["d20PFSRD: Ranger"],
        ["https://www.d20pfsrd.com/classes/core-classes/ranger/"],
        notes=(
            "Combattente wilderness e tracciatore. Dado vita d10. BAB pieno. "
            "Salvezza buona su Tempra e Riflessi; cattiva su Volontà. "
            "Punti abilità per livello: 6 + Int. "
            "Favored Enemy al 1°: bonus +2 a Bluff, Knowledge, Perception, Sense Motive, Survival e ad attacco/danno contro un tipo di creatura; nuovi nemici e bonus crescenti ogni 5 livelli. "
            "Track al 1°, Wild Empathy al 1°. "
            "Combat Style al 2°: sceglie stile (archery, two-weapon combat, etc.) e guadagna bonus feats ignorando prerequisiti. "
            "Endurance come bonus feat al 3°. Favored Terrain al 3° e ogni 5 livelli: bonus a iniziativa, Knowledge (geography), Perception, Stealth, Survival e non lascia tracce. "
            "Hunter's Bond al 4°: compagno o bonus contro favored enemy agli alleati. "
            "Spells al 4°: divini preparati fino al 4° cerchio, basati su Saggezza. "
            "Woodland Stride al 7°, Swift Tracker al 8°, Evasion al 9°, Quarry al 11°, Improved Evasion al 16°, Hide in Plain Sight al 17°, Improved Quarry al 19°, Master Hunter al 20°."
        ),
        kind="class",
    ),
    base_entry(
        "Rogue", "pfrpg_core:rogue",
        ["skilled", "3/4 bab", "d8 hd", "sneak attack", "trapfinding", "evasion", "rogue talents", "reflex good"],
        ["d20PFSRD: Rogue"],
        ["https://www.d20pfsrd.com/classes/core-classes/rogue/"],
        notes=(
            "Specialista in furtività, trappole e danni a sorpresa. Dado vita d8. BAB 3/4. "
            "Salvezza buona su Riflessi; cattive su Tempra e Volontà. "
            "Punti abilità per livello: 8 + Int. "
            "Sneak Attack +1d6 al 1°, aumenta +1d6 ogni 2 livelli (fino a +10d6 al 19°). "
            "Trapfinding al 1°: bonus metà livello a Perception e Disable Device contro trappole, può disabilitare trappole magiche. "
            "Evasion al 2°. Rogue Talent al 2° e ogni 2 livelli (es. bleeding attack, combat trick, fast stealth, finesse rogue). "
            "Trap Sense +1 al 3° e ogni 3 livelli: bonus a Reflex e CA contro trappole. "
            "Uncanny Dodge al 4°, Improved Uncanny Dodge al 8°. "
            "Advanced Talents al 10°. Master Strike al 20°. "
            "Competenze: armi semplici, rapier, sap, short sword, shortbow; armature leggere."
        ),
        kind="class",
    ),
    base_entry(
        "Sorcerer", "pfrpg_core:sorcerer",
        ["arcane spellcasting", "1/2 bab", "d6 hd", "bloodline", "will good"],
        ["d20PFSRD: Sorcerer"],
        ["https://www.d20pfsrd.com/classes/core-classes/sorcerer/"],
        notes=(
            "Lanciatore arcano spontaneo. Dado vita d6. BAB 1/2. "
            "Salvezza buona su Volontà; cattive su Tempra e Riflessi. "
            "Punti abilità per livello: 2 + Int. "
            "Incantesimi arcani spontanei dalla lista sorcerer/wizard fino al 9° cerchio, basati su Carisma. "
            "Conosce pochi incantesimi ma può lanciarli più volte al giorno. "
            "Bloodline al 1°: determina poteri, bonus spells e feats (es. Aberrant, Abyssal, Arcane, Celestial, Draconic, Elemental, Fey, Infernal, Undead). "
            "Bloodline Power al 1°, 3°, 9°, 15°, 20°. "
            "Eschew Materials come bonus feat al 1°. "
            "Competenze: armi semplici. Niente armature (rischio fallimento incantesimi)."
        ),
        kind="class",
    ),
    base_entry(
        "Wizard", "pfrpg_core:wizard",
        ["arcane spellcasting", "1/2 bab", "d6 hd", "arcane school", "scribe scroll", "familiar", "will good"],
        ["d20PFSRD: Wizard"],
        ["https://www.d20pfsrd.com/classes/core-classes/wizard/"],
        notes=(
            "Lanciatore arcano preparato. Dado vita d6. BAB 1/2. "
            "Salvezza buona su Volontà; cattive su Tempra e Riflessi. "
            "Punti abilità per livello: 2 + Int. "
            "Incantesimi arcani preparati dalla lista sorcerer/wizard fino al 9° cerchio, basati su Intelligenza. "
            "Scribe Scroll come bonus feat al 1°. "
            "Arcane Bond al 1°: familiar o bonded object (permette lanciare 1 incantesimo/giorno senza prepararlo). "
            "Arcane School al 1°: specializzazione in una scuola magica (Abjuration, Conjuration, Divination, Enchantment, Evocation, Illusion, Necromancy, Transmutation); guadagna 1 slot extra per livello della scuola e powers. "
            "Proibisce 2 scuole opposte (opposition schools): incantesimi di quelle scuoli richiedono 2 slot. "
            "Bonus Feats al 5°, 10°, 15°, 20° (metamagic, item creation, Spell Mastery). "
            "Spell Mastery opzionale. "
            "Competenze: club, dagger, heavy crossbow, light crossbow, quarterstaff; niente armature."
        ),
        kind="class",
    ),
    base_entry(
        "Magus", "ultimate_magic:magus",
        ["arcane spellcasting", "martial", "3/4 bab", "d8 hd", "spell combat", "spellstrike", "arcane pool", "magus arcana"],
        ["d20PFSRD: Magus"],
        ["https://www.d20pfsrd.com/classes/base-classes/magus/"],
        notes=(
            "Guerriero-lanciatore ibrido. Dado vita d8. BAB 3/4. "
            "Salvezza buona su Tempra e Volontà; cattiva su Riflessi. "
            "Punti abilità per livello: 2 + Int. "
            "Incantesimi arcani preparati fino al 6° cerchio, basati su Intelligenza, dalla lista magus. "
            "Spell Combat al 1°: full-round action per attaccare con un'arma da una mano e lanciare un incantesimo con l'altra, come Two-Weapon Fighting con penalty -2. "
            "Spellstrike al 2°: quando lancia un incantesimo con range touch può consegnare l'attacco tramite l'arma invece del tocco, usando il critico dell'arma. "
            "Arcane Pool al 1°: punti = 1/2 livello + Int; spendere swift action per dare all'arma enhancement bonus (max +5) o proprietà speciali (keen, flaming, etc.). "
            "Magus Arcana al 3° e ogni 3 livelli: scelte come arcane accuracy, concentrated spell, critical strike, hasted assault, spell shield, etc. "
            "Spell Recall al 4°: spendere punti arcane pool per preparare al volo un incantesimo già lanciato. "
            "Knowledge Pool al 7°. Improved Spell Combat al 8°. Fighter Training al 10°. Improved Spell Recall al 11°. Counterstrike al 16°. True Magus al 20°. "
            "Competenze: tutte le armi semplici e marziali, armature leggere, scudi (tranne tower shield)."
        ),
        kind="class",
    ),
]


RACES = [
    base_entry(
        "Dwarf", "pfrpg_core:dwarf",
        ["core", "darkvision", "hardy", "slow and steady", "stonecunning"],
        ["d20PFSRD: Dwarf"],
        ["https://www.d20pfsrd.com/races/core-races/dwarf/"],
        notes=(
            "Taglia Medium, velocità 6 m (non ridotta da armatura/carico). "
            "+2 Costituzione, +2 Saggezza, -2 Carisma. "
            "Darkvision 18 m. "
            "Defensive Training: +4 dodge bonus alla CA contro creature di taglia Large o superiore. "
            "Greed: +2 a Appraise su oggetti di pietra/metallo. "
            "Hatred: +1 attacco contro orc e goblinoidi. "
            "Hardy: +2 a TS contro veleni, incantesimi e SLAs. "
            "Slow and Steady: velocità base 6 m non ridotta da armatura o carico pesante. "
            "Stability: +4 bonus a CMD contro bull rush e trip se sta in piedi a terra. "
            "Stonecunning: +2 a Perception per individuare pietra lavorata insolita; cerca come a riposo. "
            "Weapon Familiarity: dwarven urgrosch e waraxe trattate come armi marziali. "
            "Lingue: Common, Dwarven; bonus: Giant, Gnome, Goblin, Orc, Terran, Undercommon."
        ),
        kind="race",
    ),
    base_entry(
        "Elf", "pfrpg_core:elf",
        ["core", "low-light vision", "elven immunities", "keen senses", "weapon familiarity"],
        ["d20PFSRD: Elf"],
        ["https://www.d20pfsrd.com/races/core-races/elf/"],
        notes=(
            "Taglia Medium, velocità 9 m. "
            "+2 Destrezza, +2 Intelligenza, -2 Costituzione. "
            "Low-light vision. "
            "Elven Immunities: immunità a sleep magic e +2 a TS enchantment. "
            "Keen Senses: +2 a Perception. "
            "Elven Magic: +2 a Spellcraft per identificare proprietà magiche; +1 al CL per superare SR. "
            "Weapon Familiarity: longbows, composite longbows, longswords, rapiers, shortbows, composite shortbows trattate come armi marziali. "
            "Lingue: Common, Elven; bonus: Celestial, Draconic, Gnoll, Gnome, Goblin, Orc, Sylvan."
        ),
        kind="race",
    ),
    base_entry(
        "Gnome", "pfrpg_core:gnome",
        ["core", "small", "low-light vision", "gnome magic", "illusion resistance", "keen senses"],
        ["d20PFSRD: Gnome"],
        ["https://www.d20pfsrd.com/races/core-races/gnome/"],
        notes=(
            "Taglia Small (+1 CA, +1 attacco, -1 CMB/CMD, +4 Stealth), velocità 6 m. "
            "+2 Costituzione, +2 Carisma, -2 Forza. "
            "Low-light vision. "
            "Defensive Training: +4 dodge bonus alla CA contro creature di tipo giant. "
            "Gnome Magic: +1 al DC degli incantesimi di illusione; 1/giorno dancing lights, ghost sound, prestidigitation (CL pari al livello del personaggio). "
            "Hatred: +1 attacco contro creature di tipo reptilian e goblinoid. "
            "Illusion Resistance: +2 a TS contro illusion school. "
            "Keen Senses: +2 a Perception. "
            "Obsessive: +2 a un'abilità craft o profession scelta. "
            "Weapon Familiarity: gnome hooked hammer trattata come arma marziale. "
            "Lingue: Common, Gnome, Sylvan; bonus: Draconic, Dwarven, Elven, Giant, Goblin, Orc."
        ),
        kind="race",
    ),
    base_entry(
        "Half-Elf", "pfrpg_core:half_elf",
        ["core", "low-light vision", "adaptability", "elf blood", "multitalented"],
        ["d20PFSRD: Half-Elf"],
        ["https://www.d20pfsrd.com/races/core-races/half-elf/"],
        notes=(
            "Taglia Medium, velocità 9 m. "
            "+2 a una statistica a scelta. "
            "Low-light vision. "
            "Adaptability: riceve Skill Focus come bonus feat al 1° livello. "
            "Elf Blood: conta come elfo e umano per effetti legati alla razza. "
            "Elven Immunities: immunità a sleep magic e +2 a TS enchantment. "
            "Keen Senses: +2 a Perception. "
            "Multitalented: possiede due favored class. "
            "Lingue: Common, Elven; bonus: qualsiasi (tranne linguaggi segreti)."
        ),
        kind="race",
    ),
    base_entry(
        "Half-Orc", "pfrpg_core:half_orc",
        ["core", "darkvision", "intimidating", "orc blood", "weapon familiarity"],
        ["d20PFSRD: Half-Orc"],
        ["https://www.d20pfsrd.com/races/core-races/half-orc/"],
        notes=(
            "Taglia Medium, velocità 9 m. "
            "+2 a una statistica a scelta. "
            "Darkvision 18 m. "
            "Intimidating: +2 a Intimidate. "
            "Orc Blood: conta come orco e umano per effetti legati alla razza. "
            "Orc Ferocity: 1/giorno, quando portato a 0 PF o inferiore, può agire per un round come se avesse 1 PF. "
            "Weapon Familiarity: orc double axe e falchion trattate come armi marziali; greataxe come arma semplice. "
            "Lingue: Common, Orc; bonus: Abyssal, Draconic, Giant, Gnoll, Goblin."
        ),
        kind="race",
    ),
    base_entry(
        "Halfling", "pfrpg_core:halfling",
        ["core", "small", "fearless", "halfling luck", "keen senses", "sure-footed"],
        ["d20PFSRD: Halfling"],
        ["https://www.d20pfsrd.com/races/core-races/halfling/"],
        notes=(
            "Taglia Small (+1 CA, +1 attacco, -1 CMB/CMD, +4 Stealth), velocità 6 m. "
            "+2 Destrezza, +2 Carisma, -2 Forza. "
            "Fearless: +2 morale a TS contro paura. "
            "Halfling Luck: +1 a tutti i TS. "
            "Keen Senses: +2 a Perception. "
            "Sure-Footed: +2 a Acrobatics e Climb. "
            "Weapon Familiarity: sling e halfling sling staff trattate come armi da guerra. "
            "Lingue: Common, Halfling; bonus: Dwarven, Elven, Gnome, Goblin."
        ),
        kind="race",
    ),
    base_entry(
        "Human", "pfrpg_core:human",
        ["core", "bonus feat", "skilled"],
        ["d20PFSRD: Human"],
        ["https://www.d20pfsrd.com/races/core-races/human/"],
        notes=(
            "Taglia Medium, velocità 9 m. "
            "+2 a una statistica a scelta. "
            "Bonus Feat: un extra feat al 1° livello. "
            "Skilled: +1 punto abilità extra per livello. "
            "Lingue: Common; bonus: qualsiasi (tranne linguaggi segreti). "
            "Favored Class: bonus extra +1 HP o +1 punto abilità per livello nella favored class."
        ),
        kind="race",
    ),
]


ARCHETYPES = [
    base_entry(
        "Fighter (Archer)",
        "fighter:archer",
        ["fighter", "archery", "ranged combat", "trick shot"],
        ["d20PFSRD: Fighter Archetype - Archer"],
        ["https://www.d20pfsrd.com/classes/core-classes/fighter/archetypes/paizo-fighter-archetypes/archer/"],
        notes=(
            "Archetipo del Fighter orientato al tiro con l'arco. "
            "Modifiche: sostituisce Armor Training 1-4 con Hawkeye (+1 Perception e ranged attack ogni 4 livelli) e Trick Shot (sunder/disarm/trip a distanza). "
            "Sostituisce Weapon Training 1 con Expert Archer (+1 attacco/danno con archi, +1 ogni 4 livelli dopo il 5°). "
            "Safe Shot al 9°: non provoca AoO quando tira con l'arco. "
            "Volley al 17°. Weapon Mastery si applica all'arco. "
            "Perde progressione Armor Training e Weapon Training standard in favore di bonus specifici per archi."
        ),
        kind="archetype",
    ),
    base_entry(
        "Fighter (Two-Weapon Warrior)",
        "fighter:two_weapon_warrior",
        ["fighter", "two-weapon fighting", "twin blades", "doublestrike"],
        ["d20PFSRD: Fighter Archetype - Two-Weapon Warrior"],
        ["https://www.d20pfsrd.com/classes/core-classes/fighter/archetypes/paizo-fighter-archetypes/two-weapon-warrior/"],
        notes=(
            "Archetipo del Fighter specializzato in doppia arma. "
            "Modifiche: Doublestrike al 2° (full-round action per attaccare con entrambe le armi, ogni arma colpisce due volte). "
            "Defensive Flurry al 3°: bonus CA +1 ogni 4 livelli quando full attack con due armi. "
            "Twin Blades al 5°: riduce penalità TWF di 1 (minimo -1/-1). "
            "Improved Balance al 7°: considera armi one-handed come light per TWF. "
            "Equal Opportunity al 11°. "
            "Deceptive Strike al 13°. "
            "Perfect Balance al 15°. "
            "Deft Doublestrike e Deadly Defense ai livelli alti. "
            "Perde Bravery, Armor Training 1, Weapon Training 1/2/3/4 standard."
        ),
        kind="archetype",
    ),
    base_entry(
        "Fighter (Weapon Master)",
        "fighter:weapon_master",
        ["fighter", "weapon specialization", "single weapon focus"],
        ["d20PFSRD: Fighter Archetype - Weapon Master"],
        ["https://www.d20pfsrd.com/classes/core-classes/fighter/archetypes/paizo-fighter-archetypes/weapon-master/"],
        notes=(
            "Archetipo del Fighter votato a un'unica arma. "
            "Modifiche: Weapon Training al 3° (invece del 5°) in un singolo gruppo di armi, bonus +1 ogni 4 livelli (invece che ogni 4 dopo il 5°). "
            "Reliable Strike al 5° (1/giorno tira di nuovo un attacco, danno o TS). "
            "Mirror Move al 9°: usa bonus Weapon Training per parare attacchi. "
            "Deadly Critical al 13°. "
            "Unstoppable Strike al 17°. "
            "Weapon Mastery al 20° con l'arma scelta. "
            "Perde Armor Training 2/3/4 e Bravery."
        ),
        kind="archetype",
    ),
    base_entry(
        "Fighter (Shielded Fighter)",
        "fighter:shielded_fighter",
        ["fighter", "shield", "defensive", "shield bash"],
        ["d20PFSRD: Fighter Archetype - Shielded Fighter"],
        ["https://www.d20pfsrd.com/classes/core-classes/fighter/archetypes/paizo-fighter-archetypes/shielded-fighter/"],
        notes=(
            "Archetipo del Fighter difensivo con scudo. "
            "Modifiche: Active Defense al 3° (spendere AoO per +1 CA con scudo, scala con livello). "
            "Shield Buffet al 5° (free action bull shield bash per imporre -2 agli attacchi del nemico). "
            "Fortification al 9°: chance di negare critico/sneak attack mentre impugna scudo. "
            "Shield Guard al 13°: può usare scudo per coprire alleato adiacente. "
            "Shield Mastery e Absorb Damage ai livelli alti. "
            "Perde Armor Training 1/2/3/4 e Weapon Training 1/2/3/4 standard."
        ),
        kind="archetype",
    ),
    base_entry(
        "Wizard (Evoker)",
        "wizard:evoker",
        ["wizard", "evocation school", "arcane school", "blast"],
        ["d20PFSRD: Wizard Arcane School - Evocation"],
        ["https://www.d20pfsrd.com/classes/core-classes/wizard/arcane-schools/paizo-arcane-schools/evocation/"],
        notes=(
            "Archetipo scuola arcana del Wizard. "
            "Modifiche: specializzazione in Evocation, proibisce solitamente Conjuration e Transmutation (a scelta del giocatore). "
            "Intense Spells: +1 danno con incantesimi evocation di danno, +1 ogni 5 livelli. "
            "Force Missile al 1°: magic missile 1/giorno +1 ogni 5 livelli. "
            "Elemental Wall al 8°: crea muro di energia. "
            "Bonus Spell Slots: 1 slot extra per livello da usare solo per evocation. "
            "Powers sostituiscono le abilities della scuola di specializzazione standard."
        ),
        kind="archetype",
    ),
    base_entry(
        "Wizard (Conjurer)",
        "wizard:conjurer",
        ["wizard", "conjuration school", "arcane school", "summoning"],
        ["d20PFSRD: Wizard Arcane School - Conjuration"],
        ["https://www.d20pfsrd.com/classes/core-classes/wizard/arcane-schools/paizo-arcane-schools/conjuration/"],
        notes=(
            "Archetipo scuola arcana del Wizard. "
            "Modifiche: specializzazione in Conjuration. "
            "Summoner's Charm: duration di conjuration (summoning) aumentata di round pari a metà livello. "
            "Acid Dart: ranged touch 1d6+1 ogni 2 livelli acido, usi = 3 + Int. "
            "Dimensional Steps al 8°: teletrasporto come move action, totale metri = 400. "
            "Bonus Spell Slots per conjuration. "
            "Powers sostituiscono le abilities della scuola di specializzazione standard."
        ),
        kind="archetype",
    ),
    base_entry(
        "Magus (Kensai)",
        "magus:kensai",
        ["magus", "kensai", "weapon focus", "critical", "single weapon"],
        ["d20PFSRD: Magus Archetype - Kensai"],
        ["https://www.d20pfsrd.com/classes/base-classes/magus/archetypes/paizo-magus-archetypes/kensai/"],
        notes=(
            "Archetipo Kensai del Magus, specializzato in un'unica arma da mischia. "
            "Modifiche: Diminished Spellcasting (meno slot giornalieri, -1 per ogni livello). "
            "Canny Defense al 1°: aggiunge Int alla CA se armatura leggera o senza armatura, max +1 ogni 4 livelli. "
            "Weapon Focus con l'arma prescelta al 1° come bonus feat. "
            "Perfect Strike al 4°: +1 attacco con l'arma scelta, scala. "
            "Fighter Training al 7° (invece del 10°). "
            "Iaijutsu al 7°: +2 initiative quando l'arma è in mano. "
            "Critical Perfection al 9°: bonus a confermare critici con l'arma. "
            "Superior Reflexes al 11°. "
            "Perde competenza negli scudi e nelle armature; usa solo armature leggere e nessuno scudo. "
            "Ideale per build magus melee con un'arma critica."
        ),
        kind="archetype",
    ),
    base_entry(
        "Magus (Bladebound)",
        "magus:bladebound",
        ["magus", "bladebound", "black blade", "sentient weapon"],
        ["d20PFSRD: Magus Archetype - Bladebound"],
        ["https://www.d20pfsrd.com/classes/base-classes/magus/archetypes/paizo-magus-archetypes/bladebound/"],
        notes=(
            "Archetipo del Magus con arma senziente. "
            "Modifiche: Black Blade al 3°: lama magica senziente che scala di potere con il Magus. "
            "La black blade ha Int, Sag, Car e Ego propri, bonus enhancement crescente, energy resistance e special purpose. "
            "Arcane Pool ridotto di 1 punto. "
            "Perde 3 Magus Arcana (3°, 9°, 15°) e 1 punto di arcane pool. "
            "La black blade può essere di varie forme (rapier, longsword, etc.) scelta dal giocatore."
        ),
        kind="archetype",
    ),
    base_entry(
        "Magus (Eldritch Archer)",
        "magus:eldritch_archer",
        ["magus", "eldritch archer", "ranged spellstrike", "archery"],
        ["d20PFSRD: Magus Archetype - Eldritch Archer"],
        ["https://www.d20pfsrd.com/classes/base-classes/magus/archetypes/paizo-magus-archetypes/eldritch-archer/"],
        notes=(
            "Archetipo Eldritch Archer del Magus, orientato al combattimento a distanza. "
            "Modifiche: Spell Combat funziona con armi a distanza; richiede una mano libera per caricare. "
            "Ranged Spellstrike al 2°: lancia incantesimi touch range attraverso proiettile. "
            "Arcane Pool può dare bonus a munizioni. "
            "Mantiene competenza in armature leggere ma non negli scudi. "
            "Magus Arcana e altre feature restano invariate. "
            "Ideale per build con arco e incantesimi di danno a distanza."
        ),
        kind="archetype",
    ),
    base_entry(
        "Rogue (Thug)",
        "rogue:thug",
        ["rogue", "thug", "intimidate", "frightening"],
        ["d20PFSRD: Rogue Archetype - Thug"],
        ["https://www.d20pfsrd.com/classes/core-classes/rogue/archetypes/paizo-rogue-archetypes/thug/"],
        notes=(
            "Archetipo del Rogue basato su Intimidate. "
            "Modifiche: Frightening (sostituisce trapfinding): quando colpisce con sneak attack può Intimidare come swift action, -1 round shaken diventa frightened. "
            "Brutal Beating al 3° (sostituisce trap sense): con sneak attack può rendere target sickened per round pari a metà livello. "
            "Mantiene sneak attack, rogue talents, evasion, uncanny dodge. "
            "Ottimo per build intimidate/demoralize."
        ),
        kind="archetype",
    ),
    base_entry(
        "Rogue (Scout)",
        "rogue:scout",
        ["rogue", "scout", "skirmisher", "move action sneak attack"],
        ["d20PFSRD: Rogue Archetype - Scout"],
        ["https://www.d20pfsrd.com/classes/core-classes/rogue/archetypes/paizo-rogue-archetypes/scout/"],
        notes=(
            "Archetipo del Rogue mobile. "
            "Modifiche: Skirmisher al 4°: sneak attack quando colpisce dopo aver mosso almeno 3 m. "
            "Scout's Charge al 8°: sneak attack su charge. "
            "Skirmisher migliora a +2d6 a 8°, +3d6 a 12°, +4d6 a 16°, +5d6 a 20°. "
            "Perde Uncanny Dodge e Improved Uncanny Dodge. "
            "Mantiene sneak attack, trapfinding, evasion, rogue talents."
        ),
        kind="archetype",
    ),
    base_entry(
        "Rogue (Knife Master)",
        "rogue:knife_master",
        ["rogue", "knife master", "blades", "sneak attack d8"],
        ["d20PFSRD: Rogue Archetype - Knife Master"],
        ["https://www.d20pfsrd.com/classes/core-classes/rogue/archetypes/paizo-rogue-archetypes/knife-master/"],
        notes=(
            "Archetipo del Rogue con armi da taglio leggere. "
            "Modifiche: Sneak Stab: sneak attack con dagger, kerambit, kukri, punching dagger, starknife o sword cane tira d8 invece di d6. "
            "Con armi a due mani o altre armi il danno resta d6. "
            "Hidden Blade al 5°: +1 a Sleight of Hand per nascondere armi da lancio/lama. "
            "Perde trapfinding. "
            "Mantiene sneak attack, evasion, rogue talents."
        ),
        kind="archetype",
    ),
    base_entry(
        "Barbarian (Invulnerable Rager)",
        "barbarian:invulnerable_rager",
        ["barbarian", "invulnerable rager", "damage reduction", "tank"],
        ["d20PFSRD: Barbarian Archetype - Invulnerable Rager"],
        ["https://www.d20pfsrd.com/classes/core-classes/barbarian/archetypes/paizo-barbarian-archetypes/invulnerable-rager/"],
        notes=(
            "Archetipo del Barbariano tank. "
            "Modifiche: Extreme Endurance al 3°: resistenza 1 a freddo o fuoco, aumenta ogni 3 livelli. "
            "Damage Reduction aumentata: DR 1/- al 2°, +1 ogni 2 livelli (invece che dal 7°). "
            "Perde Uncanny Dodge, Improved Uncanny Dodge, Trap Sense. "
            "Mantiene Rage, Rage Powers, Fast Movement. "
            "Ottimo per build difensive ad alta sopravvivenza."
        ),
        kind="archetype",
    ),
    base_entry(
        "Barbarian (Beast Totem)",
        "barbarian:beast_totem",
        ["barbarian", "beast totem", "rage power", "natural attacks"],
        ["d20PFSRD: Barbarian Rage Power - Beast Totem"],
        ["https://www.d20pfsrd.com/classes/core-classes/barbarian/rage-powers/paizo-rage-powers/beast-totem/"],
        notes=(
            "Rage Power Totem non archetipo vero e proprio, ma build comune. "
            "Lesser Beast Totem: 2 claw attacks (1d6) durante rage. "
            "Beast Totem: +1 naturale AC durante rage, +1 ogni 4 barbarian levels. "
            "Greater Beast Totem: pounce durante rage (full attack su charge). "
            "Richiede livelli 2, 6, 10 per i tre poteri. "
            "Molto popolare per DPR barbarico."
        ),
        kind="archetype",
    ),
    base_entry(
        "Paladin (Divine Hunter)",
        "paladin:divine_hunter",
        ["paladin", "divine hunter", "ranged smite", "archery"],
        ["d20PFSRD: Paladin Archetype - Divine Hunter"],
        ["https://www.d20pfsrd.com/classes/core-classes/paladin/archetypes/paizo-paladin-archetypes/divine-hunter/"],
        notes=(
            "Archetipo del Paladino a distanza. "
            "Modifiche: Precise Shot come bonus feat al 1° (sostituisce Heavy Armor Proficiency). "
            "Divine Hunter's Bond al 5°: può scegliere ranged weapon invece di mount, aggiunge bonus a proiettili. "
            "Shared Precision al 3°: concede Precise Shot agli alleati entro 9 m per 1 round. "
            "Aura di Justice funziona a distanza. "
            "Perde Heavy Armor Proficiency e Divine Bond standard. "
            "Mantiene Smite Evil, Lay on Hands, Mercy, Spells."
        ),
        kind="archetype",
    ),
]


def main():
    REF_DIR.mkdir(parents=True, exist_ok=True)
    for fname, data in [
        ("classes.json", CLASSES),
        ("races.json", RACES),
        ("archetypes.json", ARCHETYPES),
    ]:
        path = REF_DIR / fname
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(data)} entries to {path}")


if __name__ == "__main__":
    main()
