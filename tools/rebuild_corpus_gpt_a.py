#!/usr/bin/env python3
"""Rebuild onesto del corpus GPT-A — Lotto A (G1), STADIO A/B.

Tabella decisioni per-build (decisioni controller 2026-07-25, CONGELATE):
1. Budget point-buy 25 (Epic Fantasy): le 10 build oltre sono ridistribuite
   a <=25 preservando il concept (primarie alte). Le statline scritte sono
   PRE-razziali: i modificatori razziali sono applicati dai motori.
2. feat_count (10): tenuti i talenti centrali al concept, droppati gli
   accessori; prerequisiti RAW rispettati al livello (catalogo OGL Taverna;
   dove il catalogo e' piu' lasco del RAW — es. Colpo possente senza il
   prerequisito BAB +1 — si applica il RAW pieno).
3. prerequisito_non_soddisfatto (2): talento illegale al L1 sostituito con
   uno legale coerente (sostituzione dichiarata in `note`).
4. statline_duplicata (3): fighter_dwarf tiene la sua; druid_half_orc
   (SAG primaria) e ranger_halfelf skirmisher (DES primaria) ricevono
   statline NUOVE 25pb editoriali dichiarate.
5. bonus_razziale_mancante (4): stats pre-razziali + scelta flex coerente
   dichiarata via contratto `sheet_payload.bonus_razziale_flessibile`
   (E6-A6, chiave italiana FOR/DES/COS/INT/SAG/CAR).
6. strict/ fuori perimetro (dichiarato).
7. Derivati (PF/TS/CA/BAB/skill) ricalcolati dal builder `src/pc`, MAI
   mantenuti dichiarati GPT-A. Le skill GPT (solo nomi IT + totali) sono
   trattate come SCELTE: i nomi mappabili al catalogo inglese sono tenuti
   con gradi = livello (max RAW) fino a budget, i totali sono ricalcolati
   dal builder; "Conoscenze" generico non e' mappabile e viene droppato
   (dichiarato). Equip/inventario restano flavor GPT-A (il builder gira
   senza equip, CA = 10 + DES + taglia): attacco/danni/velocita' restano
   stringhe flavor fuori perimetro (dichiarato).

Limiti dichiarati del rebuild:
- archetype NON modellato dal builder (resta flavor in classi[].archetipi);
- aumenti di caratteristica ai livelli 4/8 non modellati dal builder:
  le varianti _lvl05/_lvl10 tengono la statline del livello 1;
- le varianti ereditano i talenti corretti del livello 1 (scelta legale a
  ogni livello: il tetto cresce col livello), senza nuove scelte editoriali;
  progressione[livello>1].talenti = [] (niente guadagni GPT inventati);
- wizard_human_evoker: statline GPT-A mantenuta (20pb legale) con flex INT;
  e' editoriale povera per il concept (INT 10 pre-razziale) ma legale —
  ribilanciamento fuori perimetro lotto A (dichiarato).

Difetti latenti emersi in tabella (l'oracolo si fermava al primo errore):
- bard_kitsune: anche i 3 talenti erano illegali (2 oltre slot; i 2 di
  archetipo con prerequisito Perform 5/3 gradi irraggiungibili al lv1);
- druid_half_orc e ranger_halfelf: 2 talenti su 1 consentito (nascosti
  dietro il flex mancante).

Uso: .venv/Scripts/python tools/rebuild_corpus_gpt_a.py [--dry-run] [--only STEM]
Idempotente: backup in src/data/builds/archive/ solo al primo giro;
riscrittura deterministica da tabella + builder.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUILDS_DIR = ROOT / "src" / "data" / "builds"
ARCHIVE_DIR = BUILDS_DIR / "archive"
REGISTRY_PATH = BUILDS_DIR / "_oracle_defects.json"
REBUILD_DATE = "2026-07-27"
LEVELS = {"": 1, "_lvl05": 5, "_lvl10": 10}

# ---------------------------------------------------------------------------
# TABELLA DECISIONI (dati auditabili; WORKFLOW.md §oracolo riporta la stessa
# tabella in forma leggibile). stats = statline PRE-razziali 25pb (None =
# tieni quella GPT-A, gia' legale); feats = lista corretta (None = tieni);
# flex = chiave italiana del +2 razziale a scelta (contratto E6-A6).
# ---------------------------------------------------------------------------
DECISIONS = {
    # -- feat_count_oltre_raw (10) ------------------------------------------
    "alchemist-goblin-vivisectionist": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata (utility generica, nessun prerequisito); "
            "droppato Colpo possente: prerequisito RAW Forza 13 non rispettato "
            "(FOR 12) e slot lv1 = 1"
        ),
    },
    "alchemist_goblin_bombardier": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata; droppato Colpo possente: talento "
            "da mischia off-concept per un bombardier (bombe a distanza)"
        ),
    },
    "arcanist_tiefling_hexcrafter_blood_arcanist": {
        "stats": None,
        "feats": ["Spell Focus (maledizioni)"],
        "flex": None,
        "note": (
            "tenuto Spell Focus (maledizioni) (centrale: hex del hexcrafter); "
            "droppato Accuratezza Magica (accessorio)"
        ),
    },
    "barbarian_fetchling_invulnerable_rager": {
        "stats": None,
        "feats": ["Colpo possente"],
        "flex": None,
        "note": (
            "tenuto Colpo possente (centrale melee; FOR 16 e BAB pieno: "
            "prerequisiti RAW rispettati); droppata Iniziativa migliorata"
        ),
    },
    "bloodrager-shabti-steelblood-metamagic-rager": {
        "stats": None,
        "feats": ["Colpo possente"],
        "flex": None,
        "note": (
            "tenuto Colpo possente (centrale steelblood melee; FOR 16, BAB "
            "pieno); droppata Iniziativa migliorata"
        ),
    },
    "cleric_samsaran_cloistered_evangelist": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata; droppato Colpo possente: concept "
            "evangelist bardico/social, non melee"
        ),
    },
    "druid_wayang_mooncaller_shapeshifter": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata; droppato Colpo possente: BAB +0 al "
            "lv1 (prerequisito RAW BAB +1 non raggiungibile; il catalogo "
            "Taverna lista solo Forza 13, lotto A applica il RAW pieno)"
        ),
    },
    "medium_oread_spirit_dancer_reanimated_medium": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata; droppato Colpo possente: concept "
            "caster/supporto (spirit dancer)"
        ),
    },
    "monk_vanara_qinggong_master_of_many_styles": {
        "stats": None,
        "feats": ["Scorpion Style", "Dodge"],
        "flex": None,
        "note": (
            "4 talenti su 2 consentiti (1 base + 1 bonus monk). SOSTITUZIONE: "
            "Tiger Style -> Scorpion Style (stile coerente col concept Master "
            "of Many Styles; prereq Improved Unarmed Strike concesso dal monk; "
            "Tiger Style richiede Acrobatics 3 gradi, illegale al lv1); "
            "Crane Style -> Dodge (prereq DES 13 ok; Crane richiede Acrobatics "
            "2 gradi, illegale al lv1; Dodge ne resta prerequisito per il "
            "reintegro ai livelli successivi); droppata la voce combinata "
            "'Tiger Style + Crane Style' (assente dal catalogo: non un talento)"
        ),
    },
    "wizard_elf_universalist": {
        "stats": None,
        "feats": ["Iniziativa migliorata"],
        "flex": None,
        "note": (
            "tenuta Iniziativa migliorata; droppato Colpo possente: concept "
            "caster universalista"
        ),
    },
    # -- stats_oltre_point_buy (10): statline PRE-razziali 25pb -------------
    "bard_kitsune_sound_striker_sandman": {
        "stats": {
            "FOR": 8,
            "DES": 14,
            "COS": 13,
            "INT": 12,
            "SAG": 10,
            "CAR": 18,
        },  # 25
        "feats": ["Focalizzazione Abilità: Intrattenere"],
        "flex": None,
        "note": (
            "31 -> 25pb, CAR primaria bard. Difetto latente: 3 talenti su 1; "
            "tenuta Focalizzazione Abilità: Intrattenere (Skill Focus Perform, "
            "centrale, nessun prereq); droppati Armonia Letale (Sound Striker) "
            "e Scacciare Sogni (Sandman): prereq Perform 5/3 gradi, illegali "
            "al lv1 (reintegrabili a lv5/lv3)"
        ),
    },
    "brawler_grippli_mutagenic_mauler_strangler": {
        "stats": {
            "FOR": 16,
            "DES": 16,
            "COS": 14,
            "INT": 10,
            "SAG": 13,
            "CAR": 7,
        },  # 24
        "feats": None,
        "flex": None,
        "note": "29 -> 24pb, FOR/DES primarie mutagenic mauler strangler",
    },
    "cavalier_strix_strategist_honor_guard": {
        "stats": {
            "FOR": 17,
            "DES": 13,
            "COS": 14,
            "INT": 12,
            "SAG": 10,
            "CAR": 12,
        },  # 25
        "feats": None,
        "flex": None,
        "note": "33 -> 25pb, FOR primaria honor guard, CAR secondaria strategist",
    },
    "gunslinger_strix_gun_tank": {
        "stats": {
            "FOR": 13,
            "DES": 17,
            "COS": 14,
            "INT": 10,
            "SAG": 14,
            "CAR": 8,
        },  # 24
        "feats": None,
        "flex": None,
        "note": "27 -> 24pb, DES primaria gun tank, COS secondaria",
    },
    "gunslinger_tengu_pistolero_bolt_ace": {
        "stats": {
            "FOR": 12,
            "DES": 18,
            "COS": 13,
            "INT": 10,
            "SAG": 14,
            "CAR": 8,
        },  # 25
        "feats": None,
        "flex": None,
        "note": "26 -> 25pb, DES primaria bolt ace (balestra)",
    },
    "investigator_catfolk_empiricist_psychic_detective": {
        "stats": {
            "FOR": 10,
            "DES": 16,
            "COS": 12,
            "INT": 17,
            "SAG": 12,
            "CAR": 8,
        },  # 25
        "feats": None,
        "flex": None,
        "note": "40 -> 25pb, INT primaria investigator empiricist",
    },
    "kineticist_strix_kinetic_knight_overwhelming_soul": {
        "stats": {
            "FOR": 12,
            "DES": 16,
            "COS": 13,
            "INT": 10,
            "SAG": 10,
            "CAR": 16,
        },  # 25
        "feats": None,
        "flex": None,
        "note": "33 -> 25pb, CAR (overwhelming soul) + DES (kinetic knight)",
    },
    "kineticist_suli_kinetic_knight_overwhelming_soul": {
        "stats": {
            "FOR": 14,
            "DES": 14,
            "COS": 13,
            "INT": 8,
            "SAG": 10,
            "CAR": 17,
        },  # 24
        "feats": None,
        "flex": None,
        "note": "41 -> 24pb, CAR primaria overwhelming soul (suli +2 FOR/+2 CAR)",
    },
    "magus_kitsune_bladebound_hexcrafter": {
        "stats": {
            "FOR": 10,
            "DES": 16,
            "COS": 13,
            "INT": 16,
            "SAG": 10,
            "CAR": 12,
        },  # 25
        "feats": None,
        "flex": None,
        "note": "27 -> 25pb, INT primaria magus bladebound, DES secondaria",
    },
    "witch_sylph_gravewalker_hedge_witch": {
        "stats": {
            "FOR": 8,
            "DES": 14,
            "COS": 12,
            "INT": 18,
            "SAG": 12,
            "CAR": 10,
        },  # 24
        "feats": None,
        "flex": None,
        "note": "34 -> 24pb, INT primaria witch (sylph +2 DES/+2 INT)",
    },
    # -- prerequisito_non_soddisfatto (1; l'altro e' monk_vanara sopra) -----
    "rogue_halfling_cutpurse": {
        "stats": None,
        "feats": ["Skill Focus (Sleight of Hand)"],
        "flex": None,
        "note": (
            "SOSTITUZIONE: Arma accurata -> Skill Focus (Sleight of Hand) "
            "(concept cutpurse; Arma accurata richiede BAB +1, rogue lv1 "
            "BAB +0; reintegrabile dal lv3 quando BAB >= +1)"
        ),
    },
    # -- statline_duplicata (3) + bonus_razziale_mancante (4) ---------------
    "fighter_dwarf_shielded": {
        "stats": None,
        "feats": None,
        "flex": None,
        "note": (
            "tiene la statline condivisa 16/14/14/10/12/8 (20pb legale) e i "
            "2 talenti (slot lv1 fighter = 3): e' la build che conserva la "
            "statline originaria (decisione 4)"
        ),
    },
    "druid_half_orc_feral": {
        "stats": {
            "FOR": 15,
            "DES": 13,
            "COS": 14,
            "INT": 10,
            "SAG": 17,
            "CAR": 7,
        },  # 24
        "feats": ["Iniziativa migliorata"],
        "flex": "SAG",
        "note": (
            "NUOVA statline editoriale 24pb SAG primaria (feral druid) + flex "
            "SAG -> SAG 19 finale. Difetto latente: 2 talenti su 1; tenuta "
            "Iniziativa migliorata, droppato Colpo possente (BAB +0 al lv1)"
        ),
    },
    "ranger_halfelf_skirmisher": {
        "stats": {
            "FOR": 14,
            "DES": 17,
            "COS": 13,
            "INT": 10,
            "SAG": 14,
            "CAR": 8,
        },  # 24
        "feats": ["Iniziativa migliorata"],
        "flex": "DES",
        "note": (
            "NUOVA statline editoriale 24pb DES primaria (skirmisher mobile) "
            "+ flex DES -> DES 19 finale, SAG 14 secondaria da ranger. Difetto "
            "latente: 2 talenti su 1; tenuta Iniziativa migliorata, droppato "
            "Colpo possente (concept mobile/distanza)"
        ),
    },
    "fighter_weapon_master_human": {
        "stats": None,
        "feats": None,
        "flex": "FOR",
        "note": (
            "statline GPT-A invariata (20pb legale); flex FOR -> FOR 18 "
            "(coerente weapon master); 2 talenti su 3 consentiti: legali"
        ),
    },
    "wizard_human_evoker": {
        "stats": None,
        "feats": None,
        "flex": "INT",
        "note": (
            "statline GPT-A invariata (20pb legale); flex INT (primaria da "
            "wizard). NOTA: statline editoriale povera per il concept (INT 10 "
            "pre-razziale) ma legale; ribilanciamento fuori perimetro lotto A"
        ),
    },
}

# Mappa nomi skill GPT (italiano) -> catalogo OGL (inglese). "Conoscenze"
# generico non e' mappabile onestamente: droppato (dichiarato in `note_skill`).
SKILL_MAP = {
    "Percezione": "Perception",
    "Acrobazia": "Acrobatics",
    "Conoscenze (arcana)": "Knowledge (Arcana)",
    "Conoscenze (arcane)": "Knowledge (Arcana)",
    "Disattivare Congegni": "Disable Device",
    "Furtività": "Stealth",
    "Intrattenere (canto)": "Perform",
    "Linguistica": "Linguistics",
    "Rapidità di mano": "Sleight of Hand",
    "Sapienza Magica": "Spellcraft",
}

_IT_TO_EN = {
    "FOR": "str",
    "DES": "dex",
    "COS": "con",
    "INT": "int",
    "SAG": "wis",
    "CAR": "cha",
}
_EN_TO_IT = {v: k for k, v in _IT_TO_EN.items()}
_STATS_SHORT = tuple(_IT_TO_EN)
_ALIAS_LONG = {
    "FOR": "Forza",
    "DES": "Destrezza",
    "COS": "Costituzione",
    "INT": "Intelligenza",
    "SAG": "Saggezza",
    "CAR": "Carisma",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def canon(kind: str, name: str) -> str:
    """Nome canonico del catalogo (match normalizzato, come l'oracolo)."""
    from src.pc import catalogs

    for entry in catalogs.load(kind):
        if _norm(entry["name"]) == _norm(name):
            return entry["name"]
    raise KeyError(f"{kind} sconosciuto: {name}")


def point_buy_cost(stats_it: dict) -> int:
    from src.pc import catalogs

    return sum(catalogs.ability_cost(v) for v in stats_it.values())


def _current_stats(payload: dict) -> dict:
    stats = ((payload.get("export") or {}).get("sheet_payload") or {}).get(
        "statistiche"
    ) or {}
    return {k: stats[k] for k in _STATS_SHORT if k in stats}


def _current_feats(payload: dict) -> list:
    talenti = ((payload.get("export") or {}).get("sheet_payload") or {}).get(
        "talenti"
    ) or []
    return [t if isinstance(t, str) else t.get("nome", "") for t in talenti]


def _declared_skills(payload: dict) -> list[str]:
    """Nomi skill GPT (italiano), nell'ordine dichiarato: prima la forma
    ricca `skills` (sempre popolata nel corpus), poi `skills_map`."""
    sheet = (payload.get("export") or {}).get("sheet_payload") or {}
    names = []
    for entry in sheet.get("skills") or []:
        nome = entry.get("nome") or entry.get("name")
        if nome and nome not in names:
            names.append(nome)
    for nome in (sheet.get("skills_map") or {}).keys():
        if nome not in names:
            names.append(nome)
    return names


def build_draft(
    stem: str, payload: dict, decision: dict, level: int
) -> tuple[dict, int]:
    """Draft per il builder src/pc al livello dato (stats/feats corretti,
    skill GPT mappate con gradi = livello fino a budget). Ritorna
    (draft, budget skill) — il budget e' quello RAW da classe+Int+Human."""
    from src.pc import catalogs

    stats_it = decision["stats"] or _current_stats(payload)
    feats = (
        decision["feats"] if decision["feats"] is not None else _current_feats(payload)
    )
    race = canon("races", payload["build_state"]["race"])
    class_ = canon("classes", payload["build_state"]["class"])
    int_mod = (stats_it["INT"] - 10) // 2
    per_level = catalogs.get_class(class_)["mechanics"]["skill_points_per_level"]
    budget = max(per_level + int_mod, 1) * level
    budget += level if race == "Human" else 0
    skills_en: dict[str, int] = {}
    spent = 0
    for nome in _declared_skills(payload):
        en = SKILL_MAP.get(nome)
        if en is None or en in skills_en:
            continue
        if spent + level > budget:
            continue
        skills_en[en] = level
        spent += level
    draft = {
        "name": stem,
        "method": "point-buy",
        "campaign_type": "Epic Fantasy",
        "abilities": {_IT_TO_EN[k]: v for k, v in stats_it.items()},
        "race": race,
        "class": class_,
        "level": level,
        "feats": list(feats),
        "skills": skills_en,
    }
    if decision["flex"]:
        draft["race_bonus_ability"] = _IT_TO_EN[decision["flex"]]
    return draft, budget


# ---------------------------------------------------------------------------
# Riscrittura ricorsiva del payload: stats pre-razziali ovunque, talenti
# corretti, derivati dal builder. Tutte le copie ridondanti (build_state,
# benchmark, export.sheet_payload, sheet, composite.*) restano allineate.
# ---------------------------------------------------------------------------
class _Ctx:
    def __init__(
        self,
        stats_it,
        feats,
        flex,
        sheet,
        skills_it,
        skills_it_list,
        skill_budget,
        level,
        note,
    ):
        self.stats_it = stats_it
        self.feats = feats
        self.flex = flex
        mods = {ab: (sc - 10) // 2 for ab, sc in sheet["abilities"].items()}
        dex_mod = mods["dex"]
        self.hp = sheet["hp"]
        self.saves = {
            "Tempra": sheet["saves"]["fort"],
            "Riflessi": sheet["saves"]["ref"],
            "Volontà": sheet["saves"]["will"],
        }
        self.init = sheet["initiative"]
        self.bab = sheet["bab"]
        self.ac = sheet["ac"]
        # equip vuoto nel draft: nessun bonus armatura/scudo naturale —
        # touch = CA, colto alla sprovvista = CA meno Destrezza.
        self.touch = self.ac
        self.ff = self.ac - dex_mod
        self.ac_breakdown = {
            "totale": self.ac,
            "armatura": 0,
            "destrezza": dex_mod,
            "scudo": 0,
        }
        self.skills_it = skills_it
        self.skills_it_list = skills_it_list
        self.skill_budget = skill_budget
        self.level = level
        self.note = note


def _is_stats_map(node: dict) -> bool:
    return all(k in node and isinstance(node[k], int) for k in _STATS_SHORT)


def _rewrite(node, ctx: _Ctx) -> None:
    if isinstance(node, list):
        for item in node:
            _rewrite(item, ctx)
        return
    if not isinstance(node, dict):
        return
    if _is_stats_map(node):
        for k in _STATS_SHORT:
            node[k] = ctx.stats_it[k]
            long_k = _ALIAS_LONG[k]
            if long_k in node:
                node[long_k] = ctx.stats_it[k]
            if long_k.lower() in node:
                node[long_k.lower()] = ctx.stats_it[k]
        if isinstance(node.get("level"), int):
            node["level"] = ctx.level
    for key in list(node.keys()):
        value = node[key]
        if key in ("talenti", "feat_plan") and isinstance(value, list):
            if "livello" in node:  # voce di progressione: solo il lv1 dichiara talenti
                node[key] = list(ctx.feats) if node.get("livello") == 1 else []
            else:
                node[key] = list(ctx.feats)
        elif key == "pf_totali":
            node[key] = ctx.hp
        elif key == "hp" and isinstance(value, dict) and "totali" in value:
            value["totali"] = ctx.hp
        elif key == "salvezze" and isinstance(value, dict) and "Tempra" in value:
            value.update(ctx.saves)
        elif key == "salvezze_breakdown" and isinstance(value, dict):
            for save, total in ctx.saves.items():
                if isinstance(value.get(save), dict):
                    value[save]["totale"] = total
        elif key in ("iniziativa", "init") and isinstance(value, (int, float)):
            node[key] = ctx.init
        elif key == "BAB":
            node[key] = ctx.bab
        elif key in ("ca", "CA", "AC_tot") and isinstance(value, int):
            node[key] = ctx.ac
        elif key == "CA_touch":
            node[key] = ctx.touch
        elif key == "CA_ff":
            node[key] = ctx.ff
        elif key == "ac_breakdown" and isinstance(value, dict):
            node[key] = dict(ctx.ac_breakdown)
        elif key == "skill_points":
            node[key] = ctx.skill_budget
        elif key == "skills_map":
            node[key] = dict(ctx.skills_it)
        elif key == "skills" and isinstance(value, list):
            node[key] = [dict(s) for s in ctx.skills_it_list]
    if "classi" in node and "statistiche" in node:
        # sheet_payload (tutte le copie): stats garantite anche dove la
        # sorgente GPT le ometteva (es. magus_kitsune: statistiche null),
        # contratto flex E6-A6 + provenance.
        st = node.get("statistiche")
        if not isinstance(st, dict):
            st = {}
            node["statistiche"] = st
        for k in _STATS_SHORT:
            st[k] = ctx.stats_it[k]
        if ctx.flex:
            node["bonus_razziale_flessibile"] = ctx.flex
        node["rebuild_gpt_a"] = {
            "tool": "tools/rebuild_corpus_gpt_a.py",
            "lotto": "A",
            "data": REBUILD_DATE,
            "livello": ctx.level,
            "decisione": ctx.note,
        }
    for value in node.values():
        _rewrite(value, ctx)


def rebuild_payload(
    payload: dict,
    sheet: dict,
    decision: dict,
    level: int,
    stats_it: dict,
    skills_it_pairs: list[tuple[str, dict]],
    skill_budget: int,
) -> dict:
    """Ritorna una copia del payload con stats/talenti/derivati riscritti."""
    skills_it = {nome: {"totale": s["total"]} for nome, s in skills_it_pairs}
    skills_it_list = [
        {
            "nome": nome,
            "gradi": s["ranks"],
            "mod_car": (sheet["abilities"][s["ability"]] - 10) // 2,
            "classe": s["class_skill"],
            "totale": s["total"],
        }
        for nome, s in skills_it_pairs
    ]
    feats = (
        decision["feats"] if decision["feats"] is not None else _current_feats(payload)
    )
    ctx = _Ctx(
        stats_it,
        feats,
        decision["flex"],
        sheet,
        skills_it,
        skills_it_list,
        skill_budget,
        level,
        decision["note"],
    )
    out = copy.deepcopy(payload)
    _rewrite(out, ctx)
    return out


def plan(stem: str) -> dict:
    """Piano completo di una build: payload riscritti ai 3 livelli."""
    from src.pc.engine import build_character
    from src.pc.models import CharacterDraft

    base_path = BUILDS_DIR / f"{stem}.json"
    payload = json.loads(base_path.read_text(encoding="utf-8"))
    decision = DECISIONS[stem]
    stats_it = decision["stats"] or _current_stats(payload)
    files = {}
    for suffix, level in LEVELS.items():
        draft, skill_budget = build_draft(stem, payload, decision, level)
        sheet = build_character(CharacterDraft.from_dict(draft))
        if sheet.get("errors"):
            raise ValueError(
                f"{stem} lv{level}: builder rifiuta il draft: {sheet['errors']}"
            )
        built = sheet.get("skills", {})
        pairs = [
            (nome, built[SKILL_MAP[nome]])
            for nome in _declared_skills(payload)
            if SKILL_MAP.get(nome) in built
        ]
        files[suffix] = {
            "level": level,
            "sheet": sheet,
            "payload": rebuild_payload(
                payload, sheet, decision, level, stats_it, pairs, skill_budget
            ),
        }
    return {
        "stem": stem,
        "decision": decision,
        "stats_it": stats_it,
        "old_stats": _current_stats(payload),
        "old_feats": _current_feats(payload),
        "files": files,
    }


def _print_plan(p: dict) -> None:
    d = p["decision"]
    print(f"== {p['stem']}")
    print(
        f"   stats: {p['old_stats']} (costo {point_buy_cost(p['old_stats'])})"
        f" -> {p['stats_it']} (costo {point_buy_cost(p['stats_it'])})"
    )
    new_feats = d["feats"] if d["feats"] is not None else p["old_feats"]
    print(f"   talenti: {p['old_feats']} -> {new_feats}")
    print(f"   flex: {d['flex'] or '-'} | {d['note']}")
    for suffix, info in p["files"].items():
        s = info["sheet"]
        tgt = f"{p['stem']}{suffix}.json"
        print(
            f"   lv{info['level']:>2} {tgt}: PF {s['hp']}, BAB +{s['bab']}, "
            f"init {s['initiative']:+d}, TS {s['saves']['fort']}/{s['saves']['ref']}/"
            f"{s['saves']['will']}, CA {s['ac']}, skill {len(s.get('skills', {}))}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run", action="store_true", help="mostra il piano senza scrivere nulla"
    )
    ap.add_argument(
        "--only",
        metavar="STEM",
        help="rigenera solo la build indicata (nome file senza .json)",
    )
    args = ap.parse_args()

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["defects"]
    registry_stems = {f[: -len(".json")] for f in registry}
    table_stems = set(DECISIONS)
    extra = registry_stems - table_stems
    if extra:
        print(
            "ERRORE: build nel registry difetti senza decisione in tabella:",
            sorted(extra),
        )
        return 1
    if registry_stems != table_stems:
        # Dopo il primo rebuild il registry si svuota: la tabella (scope
        # congelato del lotto A) resta la fonte dei target di rebuild.
        print(
            f"nota: registry attuale {len(registry_stems)} build, tabella "
            f"lotto A {len(table_stems)} — si procede sulla tabella."
        )

    stems = [args.only] if args.only else sorted(DECISIONS)
    n_written = 0
    for stem in stems:
        p = plan(stem)
        _print_plan(p)
        if args.dry_run:
            continue
        for suffix, info in p["files"].items():
            target = BUILDS_DIR / f"{stem}{suffix}.json"
            backup = ARCHIVE_DIR / target.name
            if target.exists() and not backup.exists():
                ARCHIVE_DIR.mkdir(exist_ok=True)
                backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
            target.write_text(
                json.dumps(info["payload"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            n_written += 1
    if not args.dry_run:
        print(f"\nScritti {n_written} file (backup originali in {ARCHIVE_DIR}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
