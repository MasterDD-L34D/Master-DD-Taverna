#!/usr/bin/env python3
"""Applica la policy PI ai feats (Task 2 di planning/2026-07-19-pi-feats-triage.md).

Pipeline deterministica e fail-closed (ogni deriva dai conteggi del triage
blocca l'applicazione):

1. **Ripristino D** (24 entry): nomi/campi mangiati dalla sanitize storica
   naive ripristinati da fonte AoN (pagine FeatDisplay in cache
   ``data/reference/aon_cache/``, lette il 2026-07-19; la tabella
   RESTORE_TABLE e' il dato verificato e committato — la riproducibilita'
   non dipende dalla cache gitignored). Ripristina nome, description
   (flavor + benefit, convenzione catalogo verificata byte-identica su
   entry di controllo), prerequisites (tag fonte ISM/ISWG/OA strippati;
   l'alternativa PI "or Varisian Tattoo" delle entry tattoo e' scartata:
   feat con nome PI assente dal catalogo OGL, convenzione fail-closed di
   enrich_feats), source/tags, references, reference_urls, source_id.
   Ricategorizzazione: 5 entry con PI vera nell'identita' (Erastil's
   Blessing, Osirionology, Osiriontologist, Pathfinder Society Ally,
   Noble Scion (Taldor Variant)) -> A -> feats_local; le altre 19 restano
   OGL (Tattoo Attunement ha "Inner Sea" nella description ripristinata:
   entra nel flusso C). Nota: "Osirionology"/"Osiriontologist" sono nomi
   composti PI-derived che il word-boundary non matcha (\\bOsirion\\b non
   matcha "Osirionology"): classificati A per identita' PI, come da policy.
2. **Fix riferimenti ai nomi ripristinati**: le stringhe corrotte residue
   (es. "Ea bardental Fist**" nei prerequisiti della famiglia genie) sono
   aggiornate al nome ripristinato (sostituzione esatta del set chiuso dei
   22 nomi D, solo campi prerequisites/references).
3. **Spostamento A+B (+D->A) in pi_local_only/feats_local.json**: entry
   complete, mosse verbatim (A/B) o post-ripristino (D->A). Il duplicato
   "LastwallPhalanx" (artifact import, description identica a
   "Lastwall Phalanx") e' rimosso per dedup.
3bis. **Policy B estesa (controller 2026-07-19)**: il prerequisito
   **vincolante PI** (etnia/organizzazione/tradizione specifica di Golarion,
   es. "human (Shoanti)", "Member of a Shoanti tribe", prereq che
   referenziano feat A della catena Aldori) equivale al prerequisito
   deita'-specifico -> la entry va in feats_local (B_EXTENDED_LOCAL, 16
   entry, ex categoria C). Eccezione documentata: il match PI nel prereq
   limitato a una **citazione di libro** (es. "The Inner Sea World Guide"
   in Harrowed Summoning) NON e' vincolante -> sanitize del testo prereq
   con il replacement neutro e la entry resta in OGL. Le entry B-estesa si
   spostano **verbatim** (description originale pre-sanitize, come A/B).
4. **Sanitize C chirurgica**: solo il campo description delle entry C
   rimaste in OGL (piu' Tattoo Attunement post-ripristino) con il tool
   word-boundary (sanitize_reference_pi). I prerequisites NON sono
   sanitizzati, tranne il caso citazione-libro di 3bis.
5. **Verifiche**: conteggi, dangling refs (con la B estesa i 3 ref
   OGL->local precedenti diventano local->local: attesi 0 residui),
   scansione word-boundary residua su feats.json **name+description+
   prerequisites = 0** (mascherando i replacement sanctioned, es.
   "the inner sea region"), unicita' source_id, idempotenza sanitize.
6. **Manifest + report**: aggiorna data/reference/manifest.json (feats
   2787, feats_local 49 local_only) e scrive reports/pi_feats_apply.md.

Uso:
  python tools/apply_pi_feats_policy.py           # dry-run: verifiche + sommario
  python tools/apply_pi_feats_policy.py --write   # applica e scrive file+report

Riproducibilita': ri-eseguibile solo dallo stato pre-policy di feats.json
(HEAD 0847fdf e precedenti): dopo l'applicazione i conteggi del triage
cambiano e il tool si ferma alla guardia iniziale (niente doppia applicazione).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.sanitize_reference_pi import (
    DESCRIPTION_ONLY_REPLACEMENTS,
    REPLACEMENTS,
    _RULES,
    _RULES_DESCRIPTION,
    sanitize_text,
)
from tools.triage_pi_feats import (
    RIPRISTINO_PROPOSTO,
    _dangling_refs,
    _find_terms,
    build_triage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATS_JSON = REPO_ROOT / "data" / "reference" / "ogl" / "feats.json"
FEATS_LOCAL_JSON = REPO_ROOT / "data" / "reference" / "pi_local_only" / "feats_local.json"
MANIFEST_JSON = REPO_ROOT / "data" / "reference" / "manifest.json"
REPORT_PATH = REPO_ROOT / "reports" / "pi_feats_apply.md"

POLICY_DATE = "2026-07-19"
UPDATED_AT = f"{POLICY_DATE}T00:00:00Z"

# Fotografia del triage (reports/pi_feats_triage.md): guardia fail-closed.
EXPECTED_ENTRIES = 2837
EXPECTED_COUNTS = {"A": 17, "B": 11, "C": 32, "D": 24}

# Duplicato da artifact di import (nome incollato, description identica):
# rimosso; l'originale "Lastwall Phalanx" (A) va in feats_local.
DEDUP_DROP = {"LastwallPhalanx": "Lastwall Phalanx"}

# Policy B estesa (controller 2026-07-19): prerequisito vincolante PI
# (etnia/organizzazione/tradizione Golarion-specifica) = prerequisito
# deita'-specifico -> feats_local. Le 16 entry (tutte ex categoria C) si
# spostano verbatim. Motivo per entry = termine PI vincolante nei prereq.
B_EXTENDED_LOCAL = {
    # Famiglia Aldori: prereq referenziano feat A (cascata policy §5)
    "Duelist Of The Roaring Falls": "aldori (prereq: Aldori Dueling Disciple, feat A)",
    "Duelist Of The Shrouded Lake": "aldori (prereq: Aldori Dueling Disciple, feat A)",
    "Falling Water Gambit": "aldori (prereq: Aldori Dueling Disciple, feat A)",
    "Garen's Discipline": "aldori (tradizione swordlord nei prereq)",
    "Redistributed Might": "aldori (tradizione swordlord nei prereq)",
    # Etnia / popolo vincolante
    "Deadly Troupe": "varisian (etnia nei prereq)",
    "Friendly Rivalry": "taldan (etnia nei prereq)",
    "Juju Way": "mwangi (etnia/religione nei prereq)",
    "Loyal To The Death": "tian (etnia nei prereq)",
    "Quah Bond": "shoanti (prereq vincolante 'human (Shoanti)'; il match 'inner sea' e' solo citazione libro)",
    "Ruthless Opportunist": "chelaxian (etnia nei prereq)",
    "Scion Of The Lost Empire": "chelaxian, taldan (etnia nei prereq)",
    "Totem Spirit": "shoanti (prereq vincolante 'Member of a Shoanti tribe')",
    "Triangulate": "kellid (etnia nei prereq)",
    # Organizzazione vincolante
    "Ominous Mien": "hellknight (ordine nei prereq)",
    "Signifer Armor Training": "hellknight (ordine nei prereq)",
}

# Match PI nel prereq SOLO come citazione di libro: NON vincolante -> la
# entry resta in OGL e il testo prereq e' sanitizzato con i replacement
# neutri (set base, mai i description-only). Evidenza in
# reports/pi_feats_apply.md § Policy B estesa.
PREREQ_CITATION_SANITIZE = {"Harrowed Summoning"}

# Riferimenti esatti OGL -> entry locali residui attesi. Con la B estesa la
# catena duelist (3 ref verso Aldori Dueling Disciple) si sposta a sua
# volta: i riferimenti diventano local->local e l'atteso e' zero.
EXPECTED_DANGLING = set()

# Nota canonica del catalogo feats_local nel manifest (fonte unica: usata
# sia in creazione sia in riallineamento anti-drift).
FEATS_LOCAL_NOTE = (
    "Feats con Product Identity nel nome o nei prerequisiti "
    "(categorie A/B + B estesa: prereq vincolante PI + D "
    "PI-identity), spostati dal catalogo OGL con la policy "
    "2026-07-19 (reports/pi_feats_apply.md). NON "
    "redistribuire. Generato da tools/apply_pi_feats_policy.py; "
    "indicizza con tools/index_rag.py --include-local.")

# Header del catalogo locale (pattern monsters_local.json).
FEATS_LOCAL_HEADER = {
    "_license": "OGL-1.0a",
    "_source": "Archives of Nethys (aonprd.com) / d20pfsrd — feats PI "
               "spostati dal catalogo OGL (policy 2026-07-19, Task 2); "
               "local only, not redistributed",
}

# Replacement sanctioned: i valori neutrali che possono ancora contenere un
# termine PI letterale (es. "the inner sea region" contiene "inner sea").
# Mascherati nella scansione residua (documentato nel report).
_SANCTIONED_MASK = sorted(
    {new for _, new in REPLACEMENTS + DESCRIPTION_ONLY_REPLACEMENTS},
    key=len, reverse=True,
)

# Tabella di ripristino delle 24 entry D, verificata contro le pagine AoN
# (FeatDisplay) in cache il 2026-07-19. Chiave: nome corrente corrotto;
# "disposition": local = identita' PI (-> feats_local), ogl = resta nel
# catalogo OGL. Generata e verificata a mano; NON dipende dalla cache a
# runtime. Le 2 entry tattoo mantengono il nome (ripristino di testo e
# prerequisiti). Iniettata sotto come JSON (ascii-escaped).
RESTORE_TABLE = json.loads(r"""{"Ea bardental Channel": {"name": "Elemental Channel","source": "PRPG Core Rulebook","tags": ["PRPG Core Rulebook"],"prerequisites": ["Channel energy class feature"],"description": "Choose one elemental subtype, such as air, earth, fire, or water. You can channel your divine energy to harm or heal outsiders that possess your chosen elemental subtype.\n\nInstead of its normal effect, you can choose to have your ability to channel energy heal or harm outsiders of your chosen elemental subtype. You must make this choice each time you channel energy. If you choose to heal or harm creatures of your elemental subtype, your channel energy has no affect on other creatures. The amount of damage healed or dealt and the DC to halve the damage is otherwise unchanged.","references": ["Archives of a deity of magic: Elemental Channel"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Channel"],"source_id": "prpg_core_rulebook:elemental_channel","disposition": "ogl"},"Ea bardental Commixture": {"name": "Elemental Commixture","source": "Blood Of The Elements","tags": ["Blood Of The Elements"],"prerequisites": ["Caster level 1st"],"description": "You can combine your elemental spells with those of your allies to produce entirely new and synergistic magical effects.\n\nYou and an ally within 30 feet who shares this feat can cast your spells together to create a more powerful, hybrid effect. Both spells must have an elemental descriptor (air, earth, fire, or water), or an energy descriptor that corresponds to one of the elements (acid [earth], cold [water], electricity [air], or fire [fire]) . Both spells must be at least 1st level, within 1 spell level of each other, and cast during the same initiative turn through the use of readied actions.\n\nWhen the spells to be commixed are cast, one is designated as the primary spell (typically the higherlevel spell), while the other is the secondary spell. The primary spell must be an offensive spell that targets an area or one or more creatures. The secondary spell can be any spell with an appropriate descriptor. Neither spell can take more than a standard action to cast. The primary spell behaves as written (with the exception of the synergistic benefits that are described below). The secondary spell does not manifest any of its usual effects; instead, targeted creatures are affected by a secondary effect that is determined by the combination of the two spells' descriptors.\n\nTargeted creatures can attempt a saving throw against the primary spell as normal (assuming that a save is normally allowed), and then attempt a separate save against the secondary effect. The secondary effect's save type is described in its listing, and its save DC is equal to the normal save DC of the primary or secondary spell, whichever is lower (or, if neither spell allows a saving throw, 10 + lowest spell's level + spellcaster's primary spellcasting ability score [Int, Wis, or Cha] modifier).\n\nCommixed spells cannot be counterspelled normally. A creature with Improved Counterspell can counterspell commixed spells if both spells are correctly identified and both belong to the same school. Regardless, the secondary effects of two spells combined through Elemental Commixture cannot be counterspelled. Spell resistance still applies to the secondary effect, unless both of the commixed spells bypass spell resistance.\n\nSynergistic Benefits: The primary spell's save DC (if any) increases by 1. If either spell is normally modified by Spell Focus or Greater Spell Focus, the bonus to save DCs granted by those feats stacks with this increase. The caster of the primary spell also gains a +1 bonus on any caster level check made to overcome spell resistance.\n\nSecondary Effects: While the secondary spell has no direct effect other than bolstering the effects of the primary spell, the combination of spells also creates a unique secondary effect depending on the elemental descriptors of the commixed spells. For the purpose of this secondary effect, the acid, cold, and electricity descriptors count as earth, water, and air descriptors, respectively. Commixed spells with the same elemental descriptors do not produce a secondary effect, though the primary spell still gains the synergistic benefits described above. Dust (Air/Earth): Choked by dust, the targets must succeed at a Fortitude save or become staggered for 1 round plus 1 round per 5 caster levels of the secondary spell's caster. Targeted spellcasters must succeed at a concentration check to cast spells (the DC is equal to the save DC). On a successful save, the targets are not staggered but must still attempt concentration checks.Lava (Earth/Fire): The targets are splattered with bits of molten rock and take 1d6 points of fire damage. The targets must succeed at a Reflex save or catch fire (see Catching on Fire on page 444 of the Pathfinder RPG Core Rulebook).Mud (Earth/Water): The targets must succeed at a Reflex save or fall prone and have their movement speeds cut in half (to a minimum speed of 5 feet) for 1 round plus 1 round per 5 caster levels of the secondary spell's caster. On a successful save, the targets' movement speeds are cut in half for 1 round.Smoke (Air/Fire): The targets suffer smoke inhalation and must succeed at Fortitude saves or become nauseated for 1 round and blinded for 1d4 rounds. Success negates the nausea effect and reduces the blindness to 1 round. Creatures immune to fire are immune to the nausea effect.Snow (Air/Water): The primary spell gains the cold descriptor if it doesn't have that descriptor already, and half the damage dealt (if any) is cold damage. The targets must succeed at a Reflex save or fall prone.Steam (Fire/Water): Damage caused by the primary spell (if any) is treated as nonlethal, untyped damage (neither cold nor fire damage) and is not affected by energy resistance or absorbed by protection from energy. The targets become blinded for 1d4 rounds unless they succeed at a Will save.","references": ["Archives of a deity of magic: Elemental Commixture"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Commixture"],"source_id": "blood_of_the_elements:elemental_commixture","disposition": "ogl"},"Ea bardental Fist": {"name": "Elemental Fist","source": "Advanced Player's Guide","tags": ["Advanced Player's Guide"],"prerequisites": ["Con 13","Wis 13","Improved Unarmed Strike","base attack bonus +8"],"description": "You empower your strike with elemental energy\n\nWhen you use Elemental Strike pick one of the following energy types: acid, cold, electricity, or fire. On a successful hit, the attack deals damage normally plus 1d6 points of damage of the chosen type. You must declare that you are using this feat before you make your attack roll (thus a failed attack roll ruins the attempt). You may attempt an elemental fist attack once per day for every four levels you have attained (see Special), and no more than once per round.","references": ["Archives of a deity of magic: Elemental Fist"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Fist"],"source_id": "advanced_player_s_guide:elemental_fist","disposition": "ogl"},"Ea bardental Focus": {"name": "Elemental Focus","source": "Advanced Player's Guide","tags": ["Advanced Player's Guide"],"prerequisites": [],"description": "Your spells of a certain element are more difficult to resist.\n\nChoose one energy type (acid, cold, electricity, or fire). Add +1 to the Difficulty Class for all saving throws against spells that deal damage of the energy type you select.","references": ["Archives of a deity of magic: Elemental Focus"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Focus"],"source_id": "advanced_player_s_guide:elemental_focus","disposition": "ogl"},"Ea bardental Jaunt": {"name": "Elemental Jaunt","source": "Advanced Race Guide","tags": ["Advanced Race Guide"],"prerequisites": ["Character level 15th","ifrit","oread","sylph","or undine"],"description": "The spirits of your ancestral home call to you, beckoning you to return.\n\nOnce per day, you can cast plane shift as a spell-like ability with a caster level equal to your level to transport yourself and willing targets to an elemental plane that is appropriate to your race (ifrits to the Plane of Fire, oreads to the Plane of Earth, sylphs to the Plane of Air, and undines to the Plane of Water). While on that plane, you (but not anyone transported with you) are treated as though under the effect of the spell planar adaptation.","references": ["Archives of a deity of magic: Elemental Jaunt"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Jaunt"],"source_id": "advanced_race_guide:elemental_jaunt","disposition": "ogl"},"Ea bardental Knowledge": {"name": "Elemental Knowledge","source": "Psychic Anthology","tags": ["Psychic Anthology"],"prerequisites": ["Expanded element class feature"],"description": "Your breadth of knowledge widens as you explore your connection to the elements.\n\nWhen you chose a different element from your primary element with the expanded element class feature at 7th level, you gain that element's associated skills as class skills. In addition, you gain a +1 bonus on all your element's associated skills. If you chose a third element with expanded element at 15th level, you receive these benefits for that element's associated skills as well.","references": ["Archives of a deity of magic: Elemental Knowledge"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Knowledge"],"source_id": "psychic_anthology:elemental_knowledge","disposition": "ogl"},"Ea bardental Overload": {"name": "Elemental Overload","source": "Psychic Anthology","tags": ["Psychic Anthology"],"prerequisites": ["Elemental overflow class feature","kineticist level 15th"],"description": "As you become suffused with power, you become more and more like an elemental.\n\nWhenever you have accepted at least 4 points of burn, the chance to ignore the effects of a critical hit or sneak attack increases by an additional 10%. This chance increases by an additional 5% for every 2 points of burn you accept after that. This chance can't exceed 100%. Normal: Whenever you have accepted at least 3 points of burn, your chance to ignore the effects of a critical hit or sneak attack equals 5% \u00d7 your current number of points of burn.","references": ["Archives of a deity of magic: Elemental Overload"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Overload"],"source_id": "psychic_anthology:elemental_overload","disposition": "ogl"},"Ea bardental Spell": {"name": "Elemental Spell","source": "Advanced Player's Guide","tags": ["Advanced Player's Guide"],"prerequisites": [],"description": "You can manipulate the elemental nature of your spells.\n\nChoose one energy type: acid, cold, electricity, or fire. You may replace a spell's normal damage with that energy type or split the spell's damage, so that half is of that energy type and half is of its normal type. An elemental spell uses up a spell slot one level higher than the spell's actual level.","references": ["Archives of a deity of magic: Elemental Spell"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Spell"],"source_id": "advanced_player_s_guide:elemental_spell","disposition": "ogl"},"Ea bardental Strike": {"name": "Elemental Strike","source": "the inner sea region Races","tags": ["the inner sea region Races"],"prerequisites": ["Ifrit","oread","sylph","or undine"],"description": "You draw upon your extraplanar heritage to imbue your weapons with elemental energies.\n\nAs a swift action, you can imbue your weapons with elemental energy. For 1 round, your weapons deal an additional 1 point of energy damage. The type of energy damage depends on your race: acid for oread, electricity for sylph, fire for ifrit, or cold for undine. For every 5 levels you possess, this bonus increases by 1, to a maximum of +5 at 20th level.","references": ["Archives of a deity of magic: Elemental Strike"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Strike"],"source_id": "inner_sea_races:elemental_strike","disposition": "ogl"},"Ea bardental Vigor": {"name": "Elemental Vigor","source": "the inner sea region Gods","tags": ["the inner sea region Gods"],"prerequisites": ["Worshiper of an elemental lord"],"description": "You have learned transformative secrets from communing with elemental beings.\n\nWhenever you use a polymorph effect to assume the form of an elemental you gain a rush of vital energy. You gain a number of temporary hit points equal to the caster level of the polymorph effect and you gain a +10 foot bonus to your base speed.","references": ["Archives of a deity of magic: Elemental Vigor"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Elemental%20Vigor"],"source_id": "inner_sea_gods:elemental_vigor","disposition": "ogl"},"a god of the hunt's Blessing": {"name": "Erastil's Blessing","source": "Paths Of The Righteous","tags": ["Paths Of The Righteous"],"prerequisites": ["Weapon Focus (longbow)","must be a worshiper of Erastil"],"description": "Old Deadeye's favor grants you prowess with a bow that far exceeds your own physical capabilities.\n\nYou can use your Wisdom modifier instead of your Dexterity modifier on ranged attack rolls when using a bow.","references": ["Archives of a deity of magic: Erastil's Blessing"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Erastil%27s%20Blessing"],"source_id": "paths_of_the_righteous:erastil_s_blessing","disposition": "local"},"Extra Ea bardental Assault": {"name": "Extra Elemental Assault","source": "Advanced Race Guide","tags": ["Advanced Race Guide"],"prerequisites": ["Suli"],"description": "You have unlocked greater elemental power.\n\nYour elemental assault ability lasts an additional 2 rounds per day.","references": ["Archives of a deity of magic: Extra Elemental Assault"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Extra%20Elemental%20Assault"],"source_id": "advanced_race_guide:extra_elemental_assault","disposition": "ogl"},"Flow Of Ea bardents": {"name": "Flow of Elements","source": "the inner sea region Races","tags": ["the inner sea region Races"],"prerequisites": ["Ability to cast spells; ifrit","oread","sylph","or undine"],"description": "You can spontaneously channel your ally's elemental essence, be it burning fire, freezing ice, crackling lightning, or searing acid.\n\nWhenever you're adjacent to an ifrit, oread, sylph, or undine ally who also has this feat, you can spontaneously replace or split a spell's damage when casting it, as though the spell were affected by Elemental SpellAPG (without using a higher-level spell slot). The type of energy damage depends on your ally's race: acid for oread, electricity for sylph, fire for ifrit, or cold for undine.","references": ["Archives of a deity of magic: Flow of Elements"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Flow%20of%20Elements"],"source_id": "inner_sea_races:flow_of_elements","disposition": "ogl"},"Greater Ea bardental Focus": {"name": "Greater Elemental Focus","source": "Advanced Player's Guide","tags": ["Advanced Player's Guide"],"prerequisites": ["Elemental Focus"],"description": "Choose an energy type to which you have already applied the Elemental Focus feat. Any spells you cast of this energy type are very hard to resist.\n\nAdd +1 to the Difficulty Class for all saving throws against spells that deal damage of the energy type you select. This bonus stacks with the bonus from Elemental Focus.","references": ["Archives of a deity of magic: Greater Elemental Focus"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Greater%20Elemental%20Focus"],"source_id": "advanced_player_s_guide:greater_elemental_focus","disposition": "ogl"},"Impa bardent Focus": {"name": "Implement Focus","source": "Occult Adventures","tags": ["Occult Adventures"],"prerequisites": ["Occultist level 3rd"],"description": "You are more adept at spending generic focus on focus powers from your chosen school.\n\nSelect one of your implement schools. When you spend generic focus to activate focus powers with one of that school's implements, the focus powers cost their listed amount of mental focus.","references": ["Archives of a deity of magic: Implement Focus"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Implement%20Focus"],"source_id": "occult_adventures:implement_focus","disposition": "ogl"},"Impa bardent Mastery": {"name": "Implement Mastery","source": "Magic Tactics Toolbox","tags": ["Magic Tactics Toolbox"],"prerequisites": ["Implements class feature","mental focus class feature"],"description": "You can use your implements to unlock secrets of mastering relics and other items of power.\n\nFor the purposes of using item mastery feats, you treat your implements as magic items with all spells that you know from each implement's associated implement school functioning as their effective construction requirements. When using an implement to activate an item mastery feat, you can spend a number of points of mental focus equal to half of the feat's base Fortitude save bonus prerequisite to activate the feat without counting the use against the item mastery feat's total number of daily uses.","references": ["Archives of a deity of magic: Implement Mastery"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Implement%20Mastery"],"source_id": "magic_tactics_toolbox:implement_mastery","disposition": "ogl"},"Incremental Ea bardental Assault": {"name": "Incremental Elemental Assault","source": "Advanced Race Guide","tags": ["Advanced Race Guide"],"prerequisites": ["Suli"],"description": "You may activate and quench your elemental assault ability multiple times per day.\n\nYou may use your elemental assault ability in 1-round increments, up to a maximum number of rounds per day equal to your character level. These rounds do not have to be consecutive. Activating the ability is a swift action; ending it is a free action.","references": ["Archives of a deity of magic: Incremental Elemental Assault"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Incremental%20Elemental%20Assault"],"source_id": "advanced_race_guide:incremental_elemental_assault","disposition": "ogl"},"Noble Scion a fading empire": {"name": "Noble Scion (Taldor Variant)","source": "War For The Crown Player's Guide","tags": ["War For The Crown Player's Guide"],"prerequisites": ["Charisma 13 or Child of Oppara trait","must be taken at 1st level"],"description": "You are a member of one of the significant noble families of Oppara, whether or not you remain in good standing with your family. In many cases, these families are Imperialists loyal to Maxillar Pythareus, and as such you either are a black sheep or your family has cut you off entirely.\n\nYou gain a +2 bonus on all Knowledge (nobility) checks, and Knowledge (nobility) is always a class skill for you. You also gain an additional benefit depending on which family you belong to.\n\nBasri: You come from the long line of ambassadors, diplomats, and travelers that make up the Basri, and your family maintains the strongest ties to the elven nation of Kyonin of any Taldan humans. Select one of the following as a bonus starting language: Celestial, Elven, Gnome, Sylvan. You gain proficiency in one of the following weapons: longbow (including composite), longsword, rapier, or shortbow (including composite). If you gain proficiency in all martial weapons at 1st level, you can instead select elven curve blade.\n\nClement: Your Garundi and Mwangi ancestors served Taldor proudly during the Sixth Army of Exploration and were awarded titles for their service. Your family, which has maintained their noble titles to this day, is known for keen insights and biting observations. You can substitute your Wisdom modifier for your Charisma modifier when attempting Diplomacy skill checks.\n\nCorcina: Your family came to prominence during the Second Army of Exploration, and maintains a legacy as explorers and sailors. You gain a +1 bonus on Climb and Escape Artist checks, and a +2 bonus on Survival checks to navigate.\n\nKarthis: Yours is a family of distinguished military veterans, charismatic demagogues, and xenophobic zealots. As the rest of the family becomes increasingly Imperialist, you have made no effort to remain in their good graces, but you retain the skills they taught you during a childhood of rigorous training. You can apply your Charisma modifier instead of your Dexterity modifier to Initiative checks.\n\nKastner: Your stalwart family defines itself by opposing your devil-worshiping Chelish cousins, a grudge that inspired some of Taldor's greatest healers, priests, and negotiators. You gain one additional use per day of channel energy, lay on hands, or mesmerist tricks, or 3 additional rounds of bardic music per day. You gain only one of these benefits, even if you later acquire a second class that provides one of the other class features listed.\n\nLotheed: Your family ranks include the greatest wizards and arcane scholars in Taldor, and schooling in some of the most comprehensive arcane libraries in the Inner Sea was your birthright. If your Intelligence is 11 or higher, you gain the following spell-like abilities: 1/day\u2014dancing lights, prestidigitation, read magic, unseen servant. The caster level for these effects is equal to one-half your class level.\n\nMerosett: The cunning members of your large family, a longtime fixture in Oppara's bureaucracy, specialize in tracking lineages and sidestepping red tape. You gain a +5 bonus on Bluff checks to send secret messages and Sense Motive checks to discern secret messages. You halve the time required to search through archives, navigate government offices, review contracts, or otherwise work with the complex bureaucracies your family has mastered for generations.\n\nStavian: As a close relative of the Grand Prince, yours has been a life of material comfort and indulgence, colored by constant threats and direct influence. You gain a +2 bonus on Fortitude saves against poison and on Will saves against enchantment spells of the charm and compulsion subschools.\n\nTalbot: Your starkly conservative family are merchants and entrepreneurs first and aristocrats second, willing to forgo duty if they can instead pursue profit. They condemn would-be adventurers and readily oust them from the family ranks, leaving you an outcast. You gain a +2 bonus on one Profession skill of your choice. Once per day, you can use this Profession skill in place of a single Knowledge skill check.\n\nVarima: Your family immigrated to Taldor from Vudra hundreds of years ago, and thanks to noble roots, extensive trade contacts, and an unparalleled skill in negotiation, soon developed into a steadfast fixture of Oppara's social scene. Whenever you use Diplomacy to influence a crowd or a room (but not individuals), you can roll twice and use the better result.\n\nVernisant: Your family is descended from the great general Arnisant, who commanded Taldan forces during the Shining Crusade... and they will never let anyone forget it! Their fierce Imperialist support and nationalist fervor has left you alienated from your relatives now, but their emphasis on scholarship left a mark nonetheless. You gain a +1 bonus on all Knowledge skills in which you have at least 1 rank.\n\nVinmark: Newcomers and outsiders, your Ulfen family was exalted to nobility 19 years ago, when Stavian III promoted your family patriarch to Baron of Oppara as a reward for service in the Ulfen Guard. Established aristocrats consider your family crude, choosing to leave them on the margins of Taldan politics unless a noble thinks they could use you to curry favor with the Grand Prince, but hard-won practicality and newborn cynicism grant you insight most Taldan nobles lack. Once per day when rolling a Sense Motive check, you may roll two dice and use the better result.\n\nZespire: Your family runs charities and lobbies heavily for social reform, leaving them with few friends among their Opparan peers but heartfelt support from the common folk and lesser nobility. You gain a +2 bonus on Diplomacy and Perform checks when dealing with common citizens and with nobles whose titles are limited to Lord, Lady, Knight, or Dame.","references": ["Archives of a deity of magic: Noble Scion (Taldor Variant)"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Noble%20Scion%20%28Taldor%20Variant%29"],"source_id": "war_for_the_crown_player_s_guide:noble_scion_taldor_variant","disposition": "local"},"an ancient desert kingdomology": {"name": "Osirionology","source": "People Of The Sands","tags": ["People Of The Sands"],"prerequisites": ["Knowledge (history) 1 rank","Knowledge (local) 1 rank","must be able to speak Osiriani and Ancient Osiriani"],"description": "You have a broad interest in Osirion and are something of an authority in one specialized field.\n\nPick one Intelligence-based skill. You gain a +3 bonus on all checks made using that skill in relation to Osirion or its people. In addition, you gain a +1 bonus on all other Intelligence-based skill checks made in relation to Osirion or its people.","references": ["Archives of a deity of magic: Osirionology"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Osirionology"],"source_id": "people_of_the_sands:osirionology","disposition": "local"},"an ancient desert kingdomtologist": {"name": "Osiriontologist","source": "Osirion, Land Of Pharaohs","tags": ["Osirion, Land Of Pharaohs"],"prerequisites": ["Knowledge (history) 4 ranks","Knowledge (local) 4 ranks","Speak Language (Osiriani, Ancient Osiriani)"],"description": "You are well schooled in the traditions, culture, and history of Osirion, especially the broad expanse of its long history and ancient relics.\n\nWhen in Osirion, you gain a +1 circumstance bonus to Bluff, Diplomacy, Disguise, Gather Information, Intimidate, and Perform checks. You gain a +5 bonus when using Appraise, Decipher Script, Knowledge (all skills), and Search to learn about a person, place, or item of ancient Osirion.","references": ["Archives of a deity of magic: Osiriontologist"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Osiriontologist"],"source_id": "osirion_land_of_pharaohs:osiriontologist","disposition": "local"},"an explorers' guild Ally": {"name": "Pathfinder Society Ally","source": "Agents Of Evil","tags": ["Agents Of Evil"],"prerequisites": ["Associate (Pathfinder Society)"],"description": "The Pathfinder Society grants you access to its archives in thanks for services previously rendered.\n\nThe Pathfinder Society's vast archives are available for you to exploit. In any settlement that is the size of a small town or larger, you can spend 1d4 hours researching notes from available Pathfinders to gain a +4 circumstance bonus on a single Knowledge check.","references": ["Archives of a deity of magic: Pathfinder Society Ally"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Pathfinder%20Society%20Ally"],"source_id": "agents_of_evil:pathfinder_society_ally","disposition": "local"},"Strong Impa bardent Link": {"name": "Strong Implement Link","source": "Occult Adventures","tags": ["Occult Adventures"],"prerequisites": ["Implements class feature"],"description": "Your connection to a particular implement allows you to draw on its power more efficiently even when it's not in your possession.\n\nWhen you are within 30 feet of your implement, you don't need to attempt a concentration check to cast spells associated with that implement. When you are at a greater distance, the DC for the concentration check is equal to 15 + the spell's level.","references": ["Archives of a deity of magic: Strong Implement Link"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Strong%20Implement%20Link"],"source_id": "occult_adventures:strong_implement_link","disposition": "ogl"},"Tattoo Attunement": {"name": "Tattoo Attunement","source": "Monster Summoner's Handbook","tags": ["Monster Summoner's Handbook"],"prerequisites": ["Inscribe Magical Tattoo; Spellcraft 5 ranks"],"description": "You've learned to absorb summoned creatures into temporary spell tattoos.\n\nAs a standard action, you can touch a single creature that you've summoned, instantly transforming it into a magical tattoo on your body. This tattoo takes up one magic item slot if the summoned creature is Medium or smaller, and one additional adjacent slot for each size category larger than Medium (see page 16 of Pathfinder Campaign Setting: Inner Sea Magic for rules on magical tattoos). You can have only one such tattoo at a time.\n\nWhile in tattoo form, the summoned creature can't take actions and doesn't need to eat, sleep, or breathe; it retains the remaining duration of the summoning spell used to conjure it. The creature can stay in tattoo form for a number of hours equal to your caster level. If the creature is still in tattoo form at the end of that time, the tattoo disappears, the creature is sent back to the plane from which it was summoned, and the remaining duration of the summon is wasted. As a standard action that provokes attacks of opportunity, you can cause the creature to change from a tattoo back into creature form, and appear in a square adjacent to you. The remaining duration of the spell is then expended as normal. The creature is staggered for 1 round after emerging from tattoo form. This is a supernatural ability.","references": ["Archives of a deity of magic: Tattoo Attunement"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Tattoo%20Attunement"],"source_id": "monster_summoner_s_handbook:tattoo_attunement","disposition": "ogl"},"Tattoo Transformation": {"name": "Tattoo Transformation","source": "Monster Summoner's Handbook","tags": ["Monster Summoner's Handbook"],"prerequisites": ["Inscribe Magical Tattoo; Tattoo Attunement; Spellcraft 9 ranks"],"description": "You've learned to take on some of the resistance of a summoned creature when you absorb it as a tattoo.\n\nWhen you use Tattoo Attunement on a creature you've summoned, you can gain that creature's elemental resistance as long as it is in tattoo form. If the creature has resistance to multiple elemental types, you gain only one of them. If the creature is immune to an elemental type, you gain resistance 20 to that type. For example, if the creature has resistance 10 to both fire and cold and immunity to electricity, you can gain resistance 10 to either fire or cold or resistance 20 to electricity as long as the creature is in tattoo form.","references": ["Archives of a deity of magic: Tattoo Transformation"],"reference_urls": ["https://aonprd.com/FeatDisplay.aspx?ItemName=Tattoo%20Transformation"],"source_id": "monster_summoner_s_handbook:tattoo_transformation","disposition": "ogl"}}""")

assert set(RESTORE_TABLE) >= set(RIPRISTINO_PROPOSTO), "tabella ripristino incompleta"


def _fail(msg):
    print(f"[apply-pi] ERRORE: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _sanitize_desc_verbose(text):
    """Come sanitize_text(description=True) ma ritorna anche le regole
    applicate [(old, new, count)] per il report."""
    fired = []
    out = text
    for old, pattern, new in _RULES + _RULES_DESCRIPTION:
        out, n = pattern.subn(new, out)
        if n:
            fired.append((old, new, n))
    return out, fired


def _masked_terms(text):
    """Termini PI (word-boundary) nel testo dopo aver mascherato i
    replacement sanctioned."""
    for value in _SANCTIONED_MASK:
        text = re.sub(re.escape(value), "", text, flags=re.IGNORECASE)
    return _find_terms(text)


def apply_policy(write=False):
    data = json.loads(FEATS_JSON.read_text(encoding="utf-8"))
    entries = data["entries"]
    if len(entries) != EXPECTED_ENTRIES:
        _fail(f"entry in feats.json: {len(entries)} != {EXPECTED_ENTRIES} "
              "(stato non pre-policy? doppia applicazione?)")

    rows, _, _ = build_triage(entries)
    counts = {c: sum(1 for r in rows if r["category"] == c) for c in "ABCD"}
    if counts != EXPECTED_COUNTS:
        _fail(f"conteggi triage {counts} != attesi {EXPECTED_COUNTS}")
    by_cat = {c: [r["name"] for r in rows if r["category"] == c] for c in "ABCD"}
    by_name = {e["name"]: e for e in entries}

    d_names = set(by_cat["D"])
    if d_names != set(RESTORE_TABLE):
        _fail(f"nomi D non coperti dalla tabella: {sorted(d_names ^ set(RESTORE_TABLE))}")

    # --- 1. Ripristino D -------------------------------------------------
    restored = {}  # nome corrotto -> spec tabella
    for corrupted, spec in RESTORE_TABLE.items():
        entry = by_name.get(corrupted)
        if entry is None:
            _fail(f"entry D non trovata: {corrupted}")
        if spec["name"] != corrupted:
            entry["name"] = spec["name"]
        entry["source"] = spec["source"]
        entry["tags"] = list(spec["tags"])
        entry["prerequisites"] = list(spec["prerequisites"])
        entry["description"] = spec["description"]
        entry["references"] = list(spec["references"])
        entry["reference_urls"] = list(spec["reference_urls"])
        entry["source_id"] = spec["source_id"]
        entry["updated_at"] = UPDATED_AT
        restored[corrupted] = spec

    # I nomi sono cambiati col ripristino: ricostruisce l'indice.
    by_name = {e["name"]: e for e in entries}

    # --- 2. Fix riferimenti ai nomi ripristinati (set chiuso) ------------
    name_map = {k: v["name"] for k, v in RESTORE_TABLE.items() if k != v["name"]}
    ref_fixes = []  # (entry, campo, vecchia stringa, nuova stringa)
    for entry in entries:
        if entry["name"] in {v["name"] for v in restored.values()}:
            continue  # entry ripristinate: campi gia' riscritti
        for field in ("prerequisites", "references"):
            items = entry.get(field) or []
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                s = str(item)
                new_s = s
                for corrupted, new_name in name_map.items():
                    if corrupted in new_s:
                        new_s = new_s.replace(corrupted, new_name)
                if new_s != s:
                    items[i] = new_s
                    ref_fixes.append((entry["name"], field, s, new_s))

    # --- 3. Spostamento A+B+D->A + B estesa in feats_local; dedup --------
    for dup, original in DEDUP_DROP.items():
        if by_name[dup]["description"] != by_name[original]["description"]:
            _fail(f"dedup: {dup} non e' un duplicato esatto di {original}")
    b_extended = set(B_EXTENDED_LOCAL)
    if not b_extended <= set(by_cat["C"]):
        _fail(f"B estesa fuori categoria C: {sorted(b_extended - set(by_cat['C']))}")
    d_local = {spec["name"] for spec in restored.values() if spec["disposition"] == "local"}
    moved_names = set(by_cat["A"]) | set(by_cat["B"]) | d_local | b_extended
    local_entries = [e for e in entries if e["name"] in moved_names]
    local_entries.sort(key=lambda e: e["name"].lower())
    kept_entries = [e for e in entries
                    if e["name"] not in moved_names and e["name"] not in DEDUP_DROP]
    expected_after = EXPECTED_ENTRIES - len(moved_names) - len(DEDUP_DROP)
    if len(kept_entries) != expected_after:
        _fail(f"entry post-spostamento: {len(kept_entries)} != {expected_after}")

    # --- 4. Sanitize C chirurgica (solo description delle C rimaste) ------
    c_names = [n for n in by_cat["C"]
               if n not in DEDUP_DROP and n not in b_extended]
    # D ripristinate restate OGL con PI in description -> flusso C
    # (atteso: solo Tattoo Attunement, "Inner Sea Magic").
    extra_c = []
    for spec in restored.values():
        if spec["disposition"] == "ogl" and spec["name"] not in c_names:
            if _find_terms(by_name[spec["name"]].get("description") or ""):
                extra_c.append(spec["name"])
    sanitize_log = []  # (entry, regole applicate)
    for name in sorted(set(c_names) | set(extra_c), key=str.lower):
        entry = by_name[name]
        before = entry.get("description") or ""
        after, fired = _sanitize_desc_verbose(before)
        if after != before:
            entry["description"] = after
            entry["updated_at"] = UPDATED_AT
            sanitize_log.append((name, fired))

    # Sanitize delle citazioni libro nei prereq (caso 3bis: match PI solo
    # nel titolo citato, prereq NON vincolante). Solo regole base.
    prereq_sanitize_log = []  # (entry, vecchia lista, nuova lista)
    for name in sorted(PREREQ_CITATION_SANITIZE):
        entry = by_name.get(name)
        if entry is None or entry["name"] in moved_names:
            _fail(f"prereq-citation: {name} non trovata o spostata")
        before = list(entry.get("prerequisites") or [])
        after = [sanitize_text(str(p)) for p in before]
        if after != before:
            entry["prerequisites"] = after
            entry["updated_at"] = UPDATED_AT
            prereq_sanitize_log.append((name, before, after))

    # --- 5. Verifiche -----------------------------------------------------
    problems = []
    # 5a. nessun PI nel nome delle entry OGL residue
    name_hits = [(e["name"], _find_terms(e["name"])) for e in kept_entries]
    name_hits = [(n, t) for n, t in name_hits if t]
    if name_hits:
        problems.append(f"PI residuo nei nomi OGL: {name_hits}")
    # 5b. description pulite (mask replacement sanctioned)
    desc_hits = [(e["name"], _masked_terms(e.get("description") or ""))
                 for e in kept_entries]
    desc_hits = [(n, t) for n, t in desc_hits if t]
    if desc_hits:
        problems.append(f"PI residuo nelle description OGL: {desc_hits[:10]}")
    # 5c. zero residui PI nei prerequisites (obiettivo controller: feats.json
    # OGL con 0 residui in name+description+prerequisites)
    prereq_residui = {}
    for e in kept_entries:
        text = "\n".join(str(p) for p in (e.get("prerequisites") or []))
        terms = _masked_terms(text)
        if terms:
            prereq_residui[e["name"]] = terms
    if prereq_residui:
        problems.append(f"residui PI nei prerequisites OGL: {prereq_residui}")
    # 5d. dangling refs: con la B estesa l'atteso e' zero (la catena duelist
    # e' local->local)
    dangling = _dangling_refs(kept_entries, sorted(moved_names), set())
    exact = {(o, t) for t, info in dangling.items() for (o, _f, _s) in info["exact"]}
    if exact != EXPECTED_DANGLING:
        problems.append(f"dangling OGL->local inattesi: {sorted(exact - EXPECTED_DANGLING)}; "
                        f"mancanti: {sorted(EXPECTED_DANGLING - exact)}")
    # 5e. source_id unici nel catalogo feats
    sids = [e.get("source_id") for e in kept_entries if e.get("source_id")]
    if len(sids) != len(set(sids)):
        problems.append("source_id duplicati in feats.json post-applicazione")
    # 5f. idempotenza sanitize sulle description e sui prereq toccati
    for name, _fired in sanitize_log:
        once = by_name[name]["description"]
        twice, _ = _sanitize_desc_verbose(once)
        if twice != once:
            problems.append(f"sanitize non idempotente su {name}")
    for name, _before, after in prereq_sanitize_log:
        if [sanitize_text(str(p)) for p in after] != after:
            problems.append(f"sanitize prereq non idempotente su {name}")
    # 5g. entry locali: A/B verbatim (spostate cosi' come sono) — nessun campo
    #     richiesto mancante
    for e in local_entries:
        for key in ("name", "source", "source_id", "references", "reference_urls"):
            if not e.get(key):
                problems.append(f"entry locale {e.get('name')}: campo {key} vuoto")
    if problems:
        for p in problems:
            print(f"[apply-pi] VERIFICA FALLITA: {p}", file=sys.stderr)
        raise SystemExit(1)

    summary = {
        "moved": len(local_entries),
        "moved_a": len(by_cat["A"]),
        "moved_b": len(by_cat["B"]),
        "moved_d_to_a": len(d_local),
        "moved_b_extended": len(b_extended),
        "restored_ogl": sum(1 for s in restored.values() if s["disposition"] == "ogl"),
        "dedup": len(DEDUP_DROP),
        "feats_after": len(kept_entries),
        "local_after": len(local_entries),
        "sanitized": len(sanitize_log),
        "ref_fixes": ref_fixes,
        "prereq_sanitize_log": prereq_sanitize_log,
        "dangling_ok": sorted(EXPECTED_DANGLING),
        "by_cat": by_cat,
        "restored": restored,
        "sanitize_log": sanitize_log,
        "extra_c": sorted(extra_c),
    }

    if write:
        payload = {"_license": data.get("_license"), "_source": data.get("_source"),
                   "entries": kept_entries}
        FEATS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        local_payload = dict(FEATS_LOCAL_HEADER)
        local_payload["entries"] = local_entries
        FEATS_LOCAL_JSON.parent.mkdir(parents=True, exist_ok=True)
        FEATS_LOCAL_JSON.write_text(json.dumps(local_payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        _update_manifest(summary)
        REPORT_PATH.write_text(_render_report(summary), encoding="utf-8")
        print(f"[apply-pi] scritti feats.json ({len(kept_entries)}), "
              f"feats_local.json ({len(local_entries)}), manifest, {REPORT_PATH.name}")
    return summary


def _update_manifest(summary):
    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    n_desc = 0
    feats_payload = json.loads(FEATS_JSON.read_text(encoding="utf-8"))
    for e in feats_payload["entries"]:
        if e.get("description"):
            n_desc += 1
    for catalog in manifest["catalogs"]:
        if catalog.get("file") == "ogl/feats.json":
            catalog["entries"] = summary["feats_after"]
            catalog["notes"] = (
                "Nomi e meccaniche generiche; rimossi nomi propri e riferimenti a "
                f"Golarion. {n_desc}/{summary['feats_after']} voci arricchite con "
                f"description. Policy PI 2026-07-19: {summary['local_after']} entry "
                "PI-identity spostate in pi_local_only/feats_local.json, "
                f"{len(summary['restored'])} entry ripristinate da AoN, "
                f"{summary['sanitized']} description sanitize "
                "(reports/pi_feats_apply.md).")
            catalog["last_verified"] = POLICY_DATE
    if not any(c.get("file") == "pi_local_only/feats_local.json" for c in manifest["catalogs"]):
        manifest["catalogs"].append({
            "file": "pi_local_only/feats_local.json",
            "kind": "feats_local",
            "source": "Archives of Nethys (aonprd.com) / d20pfsrd",
            "license": "OGL-1.0a",
            "is_ogc": False,
            "is_pi": False,
            "cup_allowed": False,
            "local_only": True,
            "entries": summary["local_after"],
            "notes": FEATS_LOCAL_NOTE,
            "last_verified": POLICY_DATE,
        })
    else:
        for catalog in manifest["catalogs"]:
            if catalog.get("file") == "pi_local_only/feats_local.json":
                catalog["entries"] = summary["local_after"]
                # Nota riallineata al testo canonico del tool (anti-drift).
                catalog["notes"] = FEATS_LOCAL_NOTE
                catalog["last_verified"] = POLICY_DATE
    manifest["files"]["feats"]["entries"] = summary["feats_after"]
    # Il manifest committato termina con newline (convenzione repo).
    MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


def _render_report(summary):
    """Report di applicazione (markdown, italiano), deterministico."""
    restored = summary["restored"]
    by_cat = summary["by_cat"]
    out = []
    add = out.append
    add("# Applicazione policy PI feats — " + POLICY_DATE)
    add("")
    add("> Generato da `tools/apply_pi_feats_policy.py --write` (Task 2 di "
        "`planning/2026-07-19-pi-feats-triage.md`; triage: "
        "`reports/pi_feats_triage.md`). Rieseguibile solo dallo stato "
        "pre-policy di `feats.json` (guardia fail-closed sui conteggi).")
    add("")
    add("## Conteggi")
    add("")
    add("| Misura | Valore |")
    add("| --- | ---: |")
    add(f"| feats.json prima | {EXPECTED_ENTRIES} |")
    add(f"| feats.json dopo | {summary['feats_after']} |")
    add(f"| feats_local.json | {summary['local_after']} "
        f"(A={summary['moved_a']}, B={summary['moved_b']}, D→A={summary['moved_d_to_a']}, "
        f"B estesa={summary['moved_b_extended']}) |")
    add(f"| Ripristini D | {len(restored)} "
        f"(OGL={summary['restored_ogl']}, →local={summary['moved_d_to_a']}) |")
    add(f"| Dedup (LastwallPhalanx) | {summary['dedup']} |")
    add(f"| Description sanitize (C + Tattoo Attunement) | {summary['sanitized']} |")
    add(f"| Prereq citazione-libro sanitize | {len(summary['prereq_sanitize_log'])} |")
    add(f"| Riferimenti a nomi ripristinati corretti | {len(summary['ref_fixes'])} |")
    add("")
    add("## Entry spostate in `pi_local_only/feats_local.json` ("
        + str(summary["local_after"]) + ")")
    add("")
    add("Mosse verbatim (A/B e B estesa) o post-ripristino (D→A). File gitignored "
        "(pattern `monsters_local.json`): rigenerabile con questo tool dallo "
        "stato pre-policy. Indicizzazione RAG: `tools/index_rag.py --include-local`.")
    add("")
    add("| Entry | Origine |")
    add("| --- | --- |")
    d_local_names = {s["name"] for s in restored.values() if s["disposition"] == "local"}
    for name in sorted(by_cat["A"], key=str.lower):
        add(f"| {name} | A (PI nel nome) |")
    for name in sorted(by_cat["B"], key=str.lower):
        add(f"| {name} | B (deita' nei prereq) |")
    for name in sorted(d_local_names, key=str.lower):
        add(f"| {name} | D→A (ripristinata, identita' PI) |")
    for name in sorted(B_EXTENDED_LOCAL, key=str.lower):
        add(f"| {name} | B estesa ({B_EXTENDED_LOCAL[name]}) |")
    add("")
    add("## Policy B estesa (prerequisito vincolante PI)")
    add("")
    add(f"Decisione controller 2026-07-19: un prerequisito che lega il feat a "
        f"etnia/organizzazione/tradizione specifica di Golarion equivale al "
        f"prerequisito deita'-specifico → `pi_local_only` (stessa policy "
        f"fail-closed dei traits). **{summary['moved_b_extended']} entry** "
        "spostate (tabella sopra, origine \"B estesa\"), tutte **verbatim** "
        "(description originale pre-sanitize, come A/B: in feats_local la "
        "fonte resta integrale).")
    add("")
    add("**Valutazione dei 2 casi con match \"inner sea\" in prereq** "
        "(evidenza: testo prereq reale):")
    add("")
    add("- `Harrowed Summoning` → **resta in OGL**: il prereq è "
        "\"Harrowed (Pathfinder Campaign Setting: The Inner Sea World Guide "
        "287)\" — il match \"inner sea\" e' solo nella **citazione di libro**, "
        "il prereq vincolante e' il feat `Harrowed` (presente nel catalogo "
        "OGL). Sanitizzato il testo prereq con il replacement neutro "
        "(\"...: the inner sea region World Guide 287)\").")
    add("- `Quah Bond` → **feats_local**: i prereq sono \"Totem Spirit (The "
        "Inner Sea World Guide 289)\" + \"human (Shoanti)\" — il secondo e' "
        "**vincolante d'etnia** (stessa classe di `Loyal To The Death` "
        "\"Human (Tian)\"); inoltre il feat prerequisito `Totem Spirit` e' a "
        "sua volta B estesa (cascata policy §5).")
    add("")
    add("## Ripristini da fonte AoN (24)")
    add("")
    add("Fonte: pagine `FeatDisplay.aspx` in cache `data/reference/aon_cache/` "
        "(lette il 2026-07-19); la tabella e' committata nel tool. Ripristinati "
        "nome, description (flavor + benefit, convenzione catalogo), "
        "prerequisites, source/tags, references, reference_urls, source_id. "
        "Note applicate:")
    add("")
    add("- Tag fonte AoN strippati dai prerequisiti: `ISM`, `ISWG`, `OA`, `APG`.")
    add("- Entry tattoo: alternativa PI `or Varisian Tattoo` scartata dai "
        "prerequisiti (feat con nome PI assente dal catalogo OGL; convenzione "
        "fail-closed di `enrich_feats`).")
    add("- `Elemental Fist` e `Elemental Focus`: il contenuto catalogo proveniva "
        "dalla carta **Mythic** (collisione titoli nel dataset storico); "
        "ripristinato il blocco base AoN (stessa classe del problema sistemico "
        "documentato in appendice al triage, qui in scope perche' entry D).")
    add("- `Osirionology`/`Osiriontologist`: nomi composti PI-derived non "
        "matchati dal word-boundary (\\bOsirion\\b non matcha \"Osirionology\"); "
        "classificati A per identita' PI (policy: sanitize del nome vietata).")
    add("")
    add("| Nome corrotto | Nome ripristinato | Destinazione |")
    add("| --- | --- | --- |")
    for corrupted in sorted(restored, key=str.lower):
        spec = restored[corrupted]
        dest = "feats_local (A)" if spec["disposition"] == "local" else "OGL"
        same = "" if corrupted != spec["name"] else " (testo/prereq)"
        add(f"| {corrupted} | {spec['name']}{same} | {dest} |")
    add("")
    add("## Riferimenti a nomi ripristinati corretti ("
        + str(len(summary["ref_fixes"])) + ")")
    add("")
    add("Sostituzione esatta del set chiuso dei 22 nomi D nei campi "
        "`prerequisites`/`references` delle entry non ripristinate:")
    add("")
    for name, field, old, new in summary["ref_fixes"]:
        add(f"- `{name}` [{field}]: \"{old}\" → \"{new}\"")
    add("")
    add("## Dedup")
    add("")
    add("- `LastwallPhalanx` rimosso: duplicato esatto di `Lastwall Phalanx` "
        "(artifact di import, description identica verificata); l'originale "
        "e' categoria A → feats_local.")
    add("")
    add("## Description sanitize (C + post-ripristino) ("
        + str(summary["sanitized"]) + ")")
    add("")
    add("Scope chirurgico: solo il campo `description` delle entry C rimaste "
        "in OGL (le 16 B estesa si sono spostate verbatim prima della "
        "sanitize). Tool word-boundary (`tools/sanitize_reference_pi.py`), "
        "idempotenza verificata.")
    add("")
    for name, fired in summary["sanitize_log"]:
        rules = "; ".join(f'"{old}" → "{new}" ×{n}' for old, new, n in fired)
        add(f"- `{name}`: {rules}")
    add("")
    add("## Prereq citazione-libro sanitize ("
        + str(len(summary["prereq_sanitize_log"])) + ")")
    add("")
    add("Match PI limitato alla citazione di libro (caso non vincolante, "
        "§ Policy B estesa): testo prereq sanitizzato con i replacement "
        "neutri del set base (mai i description-only):")
    add("")
    for name, before, after in summary["prereq_sanitize_log"]:
        add(f"- `{name}`: {before} → {after}")
    add("")
    add("## Riferimenti OGL → entry locali (0)")
    add("")
    add("Con la B estesa, la catena duelist (3 riferimenti esatti verso "
        "`Aldori Dueling Disciple`, documentati nella prima applicazione) si "
        "e' spostata a sua volta in feats_local: i riferimenti sono ora "
        "**local→local**. Nessun riferimento esatto residuo da entry OGL a "
        "entry locali (verifica `_dangling_refs` sullo stato finale).")
    add("")
    add("## Residui PI: 0")
    add("")
    add("Scansione word-boundary finale (lista 75 termini del triage) su "
        "`feats.json`, campi **name + description + prerequisites**: **0 "
        "residui** (mascherando i replacement sanctioned come \"the inner "
        "sea region\"). La guardia 5c del tool fallisce l'applicazione se "
        "compare qualsiasi residuo nei prerequisites.")
    add("")
    add("## Follow-up (fuori scope, documentati)")
    add("")
    add("- Corruzione sistemica delle description (~75 entry, appendice del "
        "triage: \"ea bardental\", \"setta bardent\", ...): ripristino "
        "sistematico da fonte come task dedicato di data-quality.")
    add("- Prefisso references \"Archives of a deity of magic\" in tutto il "
        "catalogo (l'ordine delle regole nel tool e' corretto da questo "
        "task; la migrazione dei dati esistenti resta follow-up).")
    add("- Campi `source`/`tags` con testo da sanitize storica (es. \"the "
        "inner sea region Gods\"): le entry A/B e B estesa sono state spostate "
        "verbatim in feats_local e il ripristino D ha corretto solo le 24 "
        "entry interessate; la migrazione globale resta follow-up (stessa "
        "classe sistemica). **Fix quality review 2026-07-19**: i campi "
        "source/tags delle 24 entry ripristinate sono allineati alla "
        "convenzione sanitize del catalogo (\"the inner sea region "
        "Gods\"/\"Races\", source_id con slug originale), come le altre "
        "entry da quei libri.")
    add("- `source`/`tags` con citazioni di libri PI mai sanitize in origine "
        "(es. \"Path Of The Hellknight\", presente identico in HEAD su 8 "
        "entry OGL residue): classe preesistente fuori scope dei fix, "
        "rilevata dalla scansione estesa ai tags; da valutare nel gate di "
        "Task 3.")
    add("- Tag `**` residui nei prerequisiti (es. \"Elemental Fist**\"): "
        "artifact di import preesistente, non PI.")
    add("")
    return "\n".join(out) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="applica e scrive feats.json, feats_local.json, manifest e report")
    args = parser.parse_args()
    summary = apply_policy(write=args.write)
    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"[apply-pi] {mode} OK: feats {EXPECTED_ENTRIES}→{summary['feats_after']}, "
          f"local {summary['local_after']} (A={summary['moved_a']} B={summary['moved_b']} "
          f"D→A={summary['moved_d_to_a']} B+={summary['moved_b_extended']}), "
          f"ripristinate {len(summary['restored'])}, "
          f"sanitize {summary['sanitized']}, "
          f"prereq_citazione {len(summary['prereq_sanitize_log'])}, "
          f"ref_fix {len(summary['ref_fixes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
