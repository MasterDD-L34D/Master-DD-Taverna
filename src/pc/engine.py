"""Motore deterministico di creazione PG lv1 (nessun LLM)."""
from src.pc import catalogs

ABILS = ("str", "dex", "con", "int", "wis", "cha")


def ability_mod(score):
    return (score - 10) // 2


def apply_abilities(draft):
    """Valida point-buy e applica i modificatori razziali.
    Ritorna dict con 'abilities' finali e 'errors'."""
    errors = []
    if draft.method != "point-buy":
        errors.append(f"metodo non supportato: {draft.method} (solo point-buy)")
        return {"abilities": {}, "errors": errors}
    budget = catalogs.campaign_budget(draft.campaign_type)
    spent = sum(catalogs.ability_cost(v) for v in draft.abilities.values())
    if spent > budget:
        errors.append(f"point-buy: {spent} punti spesi oltre il budget {budget} ({draft.campaign_type})")
    race = catalogs.get_race(draft.race)
    if race is None:
        errors.append(f"razza sconosciuta: {draft.race}")
        return {"abilities": {}, "errors": errors}
    mods = race["mechanics"].get("ability_mods", {})
    final = dict(draft.abilities)
    if mods == {"any": 2} or mods.get("any"):
        if not draft.race_bonus_ability:
            errors.append(f"race_bonus_ability obbligatorio per {draft.race}")
        elif draft.race_bonus_ability not in ABILS:
            errors.append(f"race_bonus_ability non valida: {draft.race_bonus_ability}")
        else:
            final[draft.race_bonus_ability] += mods["any"]
    for ab, bonus in mods.items():
        if ab != "any":
            final[ab] = final.get(ab, 10) + bonus
    return {"abilities": final, "errors": errors}
