"""Benchmark numerici per build Pathfinder 1E.

I target sono derivati dalla tabella "Monster Statistics by CR" del Pathfinder
Bestiary (Paizo) e dalla metodologia "Bench-Pressing" di Derklord / RPG Willikers.
Un personaggio di livello L viene confrontato con un mostro di CR = L (AMCREL).

Fonti:
- Pathfinder Bestiary: Monster Statistics by CR
  https://aonprd.com/Rules.aspx?Name=Monster%20Creation&Category=Bestiary
- Bench-Pressing: Character Creation by the Numbers
  https://rpgwillikers.wordpress.com/2015/09/29/bench-pressing-character-creation-by-the-numbers/
"""
from __future__ import annotations

from typing import Any

# Tabella Pathfinder Bestiary: statistiche medie per CR.
# hp: hit points medi
# ac: Armor Class media
# high_atk: attacco principale
# low_atk: attacco secondario
# avg_dmg: danno medio per round se tutti gli attacchi colpiscono
# primary_dc: DC abilità primaria
# good_save: bonus save "good"
# poor_save: bonus save "poor"
_MONSTER_STATS: dict[int, dict[str, int]] = {
    1: {"hp": 15, "ac": 12, "high_atk": 2, "low_atk": 1, "avg_dmg": 5, "primary_dc": 12, "good_save": 4, "poor_save": 1},
    2: {"hp": 20, "ac": 14, "high_atk": 4, "low_atk": 3, "avg_dmg": 7, "primary_dc": 13, "good_save": 5, "poor_save": 1},
    3: {"hp": 30, "ac": 15, "high_atk": 6, "low_atk": 4, "avg_dmg": 9, "primary_dc": 14, "good_save": 6, "poor_save": 2},
    4: {"hp": 40, "ac": 17, "high_atk": 8, "low_atk": 6, "avg_dmg": 12, "primary_dc": 15, "good_save": 7, "poor_save": 3},
    5: {"hp": 55, "ac": 18, "high_atk": 10, "low_atk": 7, "avg_dmg": 15, "primary_dc": 15, "good_save": 8, "poor_save": 4},
    6: {"hp": 70, "ac": 19, "high_atk": 12, "low_atk": 8, "avg_dmg": 18, "primary_dc": 16, "good_save": 9, "poor_save": 5},
    7: {"hp": 85, "ac": 20, "high_atk": 13, "low_atk": 10, "avg_dmg": 22, "primary_dc": 17, "good_save": 10, "poor_save": 6},
    8: {"hp": 100, "ac": 21, "high_atk": 15, "low_atk": 11, "avg_dmg": 26, "primary_dc": 18, "good_save": 11, "poor_save": 7},
    9: {"hp": 115, "ac": 23, "high_atk": 17, "low_atk": 12, "avg_dmg": 30, "primary_dc": 18, "good_save": 12, "poor_save": 8},
    10: {"hp": 130, "ac": 24, "high_atk": 18, "low_atk": 13, "avg_dmg": 33, "primary_dc": 19, "good_save": 13, "poor_save": 9},
    11: {"hp": 145, "ac": 25, "high_atk": 19, "low_atk": 14, "avg_dmg": 37, "primary_dc": 20, "good_save": 14, "poor_save": 10},
    12: {"hp": 160, "ac": 27, "high_atk": 21, "low_atk": 15, "avg_dmg": 41, "primary_dc": 21, "good_save": 15, "poor_save": 11},
    13: {"hp": 180, "ac": 28, "high_atk": 22, "low_atk": 16, "avg_dmg": 45, "primary_dc": 21, "good_save": 16, "poor_save": 12},
    14: {"hp": 200, "ac": 29, "high_atk": 23, "low_atk": 17, "avg_dmg": 48, "primary_dc": 22, "good_save": 17, "poor_save": 12},
    15: {"hp": 220, "ac": 30, "high_atk": 24, "low_atk": 18, "avg_dmg": 52, "primary_dc": 23, "good_save": 18, "poor_save": 13},
    16: {"hp": 240, "ac": 31, "high_atk": 26, "low_atk": 19, "avg_dmg": 60, "primary_dc": 24, "good_save": 19, "poor_save": 14},
    17: {"hp": 270, "ac": 32, "high_atk": 27, "low_atk": 20, "avg_dmg": 67, "primary_dc": 24, "good_save": 20, "poor_save": 15},
    18: {"hp": 300, "ac": 33, "high_atk": 28, "low_atk": 21, "avg_dmg": 75, "primary_dc": 25, "good_save": 20, "poor_save": 16},
    19: {"hp": 330, "ac": 34, "high_atk": 29, "low_atk": 22, "avg_dmg": 82, "primary_dc": 26, "good_save": 21, "poor_save": 16},
    20: {"hp": 370, "ac": 36, "high_atk": 30, "low_atk": 23, "avg_dmg": 90, "primary_dc": 27, "good_save": 22, "poor_save": 17},
}

# Dado vita medio per classe (valore intero arrotondato).
_HIT_DIE: dict[str, int] = {
    "barbarian": 6,
    "barbaro": 6,
    "fighter": 5,
    "guerriero": 5,
    "paladin": 5,
    "paladino": 5,
    "ranger": 5,
    "cavalier": 5,
    "magus": 4,
    "bard": 4,
    "bardo": 4,
    "cleric": 4,
    "chierico": 4,
    "druid": 4,
    "druido": 4,
    "rogue": 4,
    "ladro": 4,
    "wizard": 3,
    "mago": 3,
    "sorcerer": 3,
    "stregone": 3,
    "witch": 3,
    "strega": 3,
    "alchemist": 4,
    "alchimista": 4,
    "summoner": 4,
    "evocatore": 4,
    "inquisitor": 4,
    "inquisitore": 4,
    "oracle": 4,
    "oracolo": 4,
    "monk": 4,
    "monaco": 4,
}

# Salvataggi good per classe (nome in italiano/inglese, mappato sul salvataggio PF).
_GOOD_SAVES: dict[str, set[str]] = {
    "barbarian": {"Tempra"},
    "barbaro": {"Tempra"},
    "fighter": {"Tempra"},
    "guerriero": {"Tempra"},
    "paladin": {"Tempra", "Volonta"},
    "paladino": {"Tempra", "Volonta"},
    "ranger": {"Tempra", "Riflessi"},
    "cavalier": {"Tempra"},
    "monk": {"Tempra", "Riflessi", "Volonta"},
    "monaco": {"Tempra", "Riflessi", "Volonta"},
    "wizard": {"Volonta"},
    "mago": {"Volonta"},
    "sorcerer": {"Volonta"},
    "stregone": {"Volonta"},
    "witch": {"Volonta"},
    "strega": {"Volonta"},
    "bard": {"Riflessi", "Volonta"},
    "bardo": {"Riflessi", "Volonta"},
    "cleric": {"Tempra", "Volonta"},
    "chierico": {"Tempra", "Volonta"},
    "druid": {"Tempra", "Volonta"},
    "druido": {"Tempra", "Volonta"},
    "rogue": {"Riflessi"},
    "ladro": {"Riflessi"},
    "alchemist": {"Tempra"},
    "alchimista": {"Tempra"},
    "magus": {"Volonta"},
    "summoner": {"Volonta"},
    "evocatore": {"Volonta"},
    "inquisitor": {"Tempra", "Volonta"},
    "inquisitore": {"Tempra", "Volonta"},
    "oracle": {"Tempra", "Volonta"},
    "oracolo": {"Tempra", "Volonta"},
}


def _monster_stats(level: int) -> dict[str, int]:
    level = max(1, min(20, level))
    return _MONSTER_STATS[level]


def _tier_label(value: float, blue: float, green: float, orange: float, higher_is_better: bool = True) -> str:
    """Restituisce 'blue', 'green', 'orange' o 'red' confrontando value con i target.

    Per statistiche dove più è meglio (DPR, AC, PF, saves).
    """
    if higher_is_better:
        if value >= blue:
            return "blue"
        if value >= green:
            return "green"
        if value >= orange:
            return "orange"
        return "red"
    # Per statistiche dove minore è meglio (non usato direttamente, ma mantenuto per estensibilità).
    if value <= blue:
        return "blue"
    if value <= green:
        return "green"
    if value <= orange:
        return "orange"
    return "red"


def compute_benchmarks(level: int, focus: str | None = None) -> dict[str, Any]:
    """Calcola i target numerici per un personaggio di livello `level`.

    Ritorna un dict con:
    - level, focus
    - monster: statistiche medie del mostro di pari CR
    - attack / ac / saves / dpr / hp: target blue/green/orange/red
    - guidance: dizionario di suggerimenti per focus
    """
    stats = _monster_stats(level)
    focus = (focus or "balanced").lower()

    # Bench-Pressing vs AMCREL (CR = livello personaggio).
    # Attack: blue solo fallo su 1, green colpisci con 7+, orange con 11+.
    attack = {
        "blue": stats["ac"] - 2,
        "green": stats["ac"] - 7,
        "orange": stats["ac"] - 11,
    }

    # AC: blue mostro colpisce solo con 20 sull'attacco debole,
    # green con 15+, orange con 11+.
    ac = {
        "blue": stats["low_atk"] + 20,
        "green": stats["low_atk"] + 15,
        "orange": stats["low_atk"] + 11,
    }

    # Saves: blue falli solo su 1, green superi con 7+, orange con 11+.
    saves = {
        "blue": stats["primary_dc"] - 2,
        "green": stats["primary_dc"] - 7,
        "orange": stats["primary_dc"] - 11,
    }

    # EDV (Expected Damage Value, full attack): blue 50% HP, green 25%, orange 16.5%.
    dpr = {
        "blue": round(stats["hp"] * 0.50, 2),
        "green": round(stats["hp"] * 0.25, 2),
        "orange": round(stats["hp"] * 0.165, 2),
        "red": round(stats["hp"] * 0.10, 2),
    }

    # HP: stima ragionevole per sopravvivere a 1-2 full attacks dell'AMCREL.
    # avg_dmg è il danno medio se tutti gli attacchi colpiscono; assumiamo ~60% hit rate
    # per calcolare il danno atteso per round.
    expected_round_dmg = round(stats["avg_dmg"] * 0.6, 1)
    hp = {
        "blue": round(expected_round_dmg * 4),   # sopravvive a ~4 round
        "green": round(expected_round_dmg * 2.5), # sopravvive a ~2-3 round
        "orange": round(expected_round_dmg * 1.5), # sopravvive a ~1-2 round
        "red": round(expected_round_dmg * 0.75),   # sopravvive a meno di 1 round
    }

    benchmarks = {
        "level": level,
        "focus": focus,
        "source": "Pathfinder Bestiary Monster Statistics by CR + Bench-Pressing",
        "monster": stats,
        "attack": attack,
        "ac": ac,
        "saves": saves,
        "dpr": dpr,
        "hp": hp,
    }
    benchmarks["guidance"] = focus_guidance(focus)
    return benchmarks


def _normalize_class(class_name: str | None) -> str:
    if not class_name:
        return "fighter"
    return class_name.lower().strip()


def estimated_hp(level: int, class_name: str | None, con_mod: int = 2, favored_class_bonus: int = 0) -> int:
    """Stima realistica dei PF per classe e livello."""
    level = max(1, min(20, level))
    hd_avg = _HIT_DIE.get(_normalize_class(class_name), 4)
    # Primo livello massimo, livelli successivi medi
    return 10 + (level - 1) * (hd_avg + con_mod + favored_class_bonus)


def class_good_saves(class_name: str | None) -> set[str]:
    """Restituisce l'insieme dei salvataggi good per la classe richiesta."""
    return _GOOD_SAVES.get(_normalize_class(class_name), {"Tempra"})


def focus_guidance(focus: str | None) -> dict[str, str]:
    """Suggerimenti da includere nel prompt per orientare il LLM."""
    focus = (focus or "balanced").lower()
    base = {
        "dpr": (
            "Focus DPR: massimizza il danno per round (DPR). "
            "Scegli talenti come Power Attack, Weapon Focus, Weapon Specialization, "
            "Furious Focus, Arcane Strike o equivalenti. "
            "Privilegia armi a due mani o TWF con molti attacchi. "
            "La DPR deve essere almeno green."
        ),
        "tank": (
            "Focus tank: massimizza sopravvivenza. "
            "Scegli talenti come Toughness, Dodge, Shield Focus, Iron Will, Improved Initiative. "
            "Privilegia armature pesanti, scudi, PF alti e CA green/orange. "
            "I PF devono essere almeno green e la CA almeno orange."
        ),
        "control": (
            "Focus control: massimizza il controllo del campo di battaglia. "
            "Scegli incantesimi/abilità come Grease, Glitterdust, Stinking Cloud, Web, Hold Person, "
            "e talenti come Spell Focus, Greater Spell Focus, Augment Summons. "
            "La Save DC dei tuoi effetti deve essere almeno green. "
            "DPR è meno rilevante, ma le difese devono essere almeno orange."
        ),
        "support": (
            "Focus support: buff, guarigione e utilità. "
            "Scegli incantesimi come Bless, Haste, Prayer, Cure, e talenti come Selective Channeling, "
            "Extra Channel, Extend Spell. "
            "Le difese devono essere almeno orange e almeno una capacità di supporto green."
        ),
        "balanced": (
            "Focus bilanciato: nessuna statistica deve essere red. "
            "Almeno un'offensiva green e tutte le difese orange."
        ),
    }
    return {
        "focus": focus,
        "priority": base.get(focus, base["balanced"]),
        "acceptable_tier": "T2" if focus in {"dpr", "tank", "control"} else "T3",
    }


def evaluate_build(
    stats: dict[str, Any],
    benchmarks: dict[str, Any],
    focus: str | None = None,
) -> dict[str, Any]:
    """Valuta le statistiche di una build rispetto ai benchmark.

    `stats` deve contenere almeno le chiavi:
    - "PF": hit points
    - "CA": armor class
    - "DPR": damage per round
    - "saves": {"Tempra": int, "Riflessi": int, "Volonta": int}
    """
    focus = (focus or benchmarks.get("focus") or "balanced").lower()
    b = benchmarks

    pf = int(stats.get("PF", 0) or 0)
    ca = int(stats.get("CA", 0) or 0)
    dpr = float(stats.get("DPR", 0) or 0)
    saves = stats.get("saves", {}) or {}

    evals: dict[str, Any] = {
        "PF": {"value": pf, "tier": _tier_label(pf, b["hp"]["blue"], b["hp"]["green"], b["hp"]["orange"])},
        "CA": {"value": ca, "tier": _tier_label(ca, b["ac"]["blue"], b["ac"]["green"], b["ac"]["orange"])},
        "DPR": {"value": dpr, "tier": _tier_label(dpr, b["dpr"]["blue"], b["dpr"]["green"], b["dpr"]["orange"])},
    }

    save_tiers = {}
    for save_name in ("Tempra", "Riflessi", "Volonta"):
        val = int(saves.get(save_name, 0) or 0)
        save_tiers[save_name] = {"value": val, "tier": _tier_label(val, b["saves"]["blue"], b["saves"]["green"], b["saves"]["orange"])}
    evals["saves"] = save_tiers

    # Assegna meta_tier complessivo.
    all_tiers = [evals["PF"]["tier"], evals["CA"]["tier"], evals["DPR"]["tier"]]
    all_tiers.extend(s["tier"] for s in save_tiers.values())

    tier_order = {"blue": 4, "green": 3, "orange": 2, "red": 1}
    min_score = min(tier_order[t] for t in all_tiers)

    if min_score >= 4:
        meta_tier = "T1"
    elif min_score >= 3:
        meta_tier = "T2"
    elif min_score >= 2:
        meta_tier = "T3"
    else:
        meta_tier = "T4"

    # Focus-specific adjustments: un focus DPR/tank/control può scendere a T3 se la stat
    # principale è almeno green e non ci sono difese red.
    if meta_tier == "T4":
        if focus == "dpr" and evals["DPR"]["tier"] in ("blue", "green") and all(t != "red" for t in all_tiers):
            meta_tier = "T3"
        elif focus == "tank" and evals["PF"]["tier"] in ("blue", "green") and evals["CA"]["tier"] != "red" and all(t != "red" for t in all_tiers):
            meta_tier = "T3"
        elif focus == "control" and "red" not in (evals["CA"]["tier"], save_tiers["Volonta"]["tier"], save_tiers["Tempra"]["tier"]):
            # Per control la DPR può essere red purché le difese siano solide.
            meta_tier = "T3"
        elif focus == "support" and "red" not in (evals["CA"]["tier"], save_tiers["Volonta"]["tier"], save_tiers["Tempra"]["tier"]):
            # Per support la DPR può essere red purché le difese siano solide.
            meta_tier = "T3"

    notes = []
    if evals["DPR"]["tier"] == "red":
        notes.append("DPR sotto la soglia orange; la build fatica a contribuire in combattimento.")
    if evals["CA"]["tier"] == "red":
        notes.append("CA troppo bassa per il livello; il personaggio verrà colpito troppo spesso.")
    if any(s["tier"] == "red" for s in save_tiers.values()):
        bad = [name for name, s in save_tiers.items() if s["tier"] == "red"]
        notes.append(f"Salvataggi critici troppo bassi: {', '.join(bad)}.")

    return {
        "meta_tier": meta_tier,
        "metrics": evals,
        "notes": notes,
        "benchmarks": {
            "hp": b["hp"],
            "ac": b["ac"],
            "dpr": b["dpr"],
            "saves": b["saves"],
        },
    }


def format_benchmarks_for_prompt(benchmarks: dict[str, Any]) -> str:
    """Formatta i benchmark per essere inclusi nel prompt LLM."""
    lines = [
        "=== BENCHMARK NUMERICI PER IL LIVELLO ===",
        f"Livello: {benchmarks['level']}  |  Focus: {benchmarks['focus']}",
        f"AMCREL (mostro CR {benchmarks['level']}): HP={benchmarks['monster']['hp']}, AC={benchmarks['monster']['ac']}, "
        f"attacco alto +{benchmarks['monster']['high_atk']}, attacco basso +{benchmarks['monster']['low_atk']}, "
        f"DC abilità {benchmarks['monster']['primary_dc']}",
        "",
        "Target per il personaggio (Bench-Pressing):",
        f"  CA:     blue ≥ {benchmarks['ac']['blue']}, green ≥ {benchmarks['ac']['green']}, orange ≥ {benchmarks['ac']['orange']}",
        f"  Attack: blue ≥ +{benchmarks['attack']['blue']}, green ≥ +{benchmarks['attack']['green']}, orange ≥ +{benchmarks['attack']['orange']}",
        f"  DPR:    blue ≥ {benchmarks['dpr']['blue']}, green ≥ {benchmarks['dpr']['green']}, orange ≥ {benchmarks['dpr']['orange']}",
        f"  Saves:  blue ≥ +{benchmarks['saves']['blue']}, green ≥ +{benchmarks['saves']['green']}, orange ≥ +{benchmarks['saves']['orange']}",
        f"  PF:     blue ≥ {benchmarks['hp']['blue']}, green ≥ {benchmarks['hp']['green']}, orange ≥ {benchmarks['hp']['orange']}",
        "",
        f"Priorità focus: {benchmarks['guidance']['priority']}",
        "=== FINE BENCHMARK ===",
    ]
    return "\n".join(lines)
