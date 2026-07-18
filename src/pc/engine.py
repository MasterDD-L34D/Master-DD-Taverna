"""Motore deterministico di creazione PG lv1 (nessun LLM)."""
from src.pc import catalogs

ABILS = ("str", "dex", "con", "int", "wis", "cha")

FEAT_BONUS_CLASSES = {"Fighter"}


def _check_prereq(prereq, ctx):
    """Valuta un prerequisito testuale. Ritorna (ok, nota)."""
    import re
    text = prereq.rstrip(".")
    m = re.match(r"^(Str|Dex|Con|Int|Wis|Cha)\w*\s+(\d+)$", text, re.I)
    if m:
        ab = m.group(1)[:3].lower()
        need = int(m.group(2))
        return ctx["abilities"][ab] >= need, f"richiede {m.group(1)} {need}"
    m = re.match(r"^base attack bonus \+(\d+)$", text, re.I)
    if m:
        return ctx["bab"] >= int(m.group(1)), f"richiede BAB +{m.group(1)}"
    if catalogs.find_feat(text) is not None:
        return text in ctx["feats"], f"richiede il talento {text}"
    m = re.search(r"level\s+(\d+)(?:st|nd|rd|th)", text, re.I)
    if m:
        needed = int(m.group(1))
        return needed <= 1, f"richiede livello {needed} (personaggio lv1)"
    if "proficien" in text.lower():
        return True, f"proficiency: {text} (assunta da classe)"
    if re.search(r"rank", text, re.I):
        return True, f"skill rank: {text} (verificata a mano)"
    return True, f"forma prerequisito non valutabile: {text}"  # warning, non errore


def validate_feats(draft, sheet):
    """Conta talenti consentiti e valuta i prerequisiti noti."""
    ctx = {"abilities": dict(sheet["abilities"]), "bab": sheet["bab"], "feats": list(draft.feats)}
    allowed = 1 + (1 if draft.race == "Human" else 0) + (1 if draft.class_ in FEAT_BONUS_CLASSES else 0)
    if len(draft.feats) > allowed:
        sheet["errors"].append(f"feat: {len(draft.feats)} selezionati su {allowed} consentiti al lv1")
    for name in draft.feats:
        feat = catalogs.find_feat(name)
        if feat is None:
            sheet["errors"].append(f"talento sconosciuto: {name}")
            continue
        for prereq in feat.get("prerequisites", []):
            ok, note = _check_prereq(prereq, ctx)
            if not ok:
                sheet["errors"].append(f"{name}: prerequisito non soddisfatto ({note})")
            elif "non valutabile" in note:
                sheet["warnings"].append(f"{name}: {note}")


def ability_mod(score):
    return (score - 10) // 2


def apply_abilities(draft):
    """Valida point-buy e applica i modificatori razziali.
    Ritorna dict con 'abilities' finali e 'errors'."""
    errors = []
    if draft.method != "point-buy":
        errors.append(f"metodo non supportato: {draft.method} (solo point-buy)")
        return {"abilities": {}, "errors": errors}
    if set(draft.abilities) != set(ABILS):
        errors.append(f"abilities: attese {sorted(ABILS)}, ricevute {sorted(draft.abilities)}")
    for ab, score in draft.abilities.items():
        if not isinstance(score, int) or not 7 <= score <= 18:
            errors.append(f"abilities[{ab}] non valida: {score!r} (atteso int 7..18)")
    try:
        budget = catalogs.campaign_budget(draft.campaign_type)
    except KeyError:
        errors.append(f"campaign_type sconosciuto: {draft.campaign_type}")
    if errors:
        return {"abilities": {}, "errors": errors}
    spent = sum(catalogs.ability_cost(v) for v in draft.abilities.values())
    if spent > budget:
        errors.append(f"point-buy: {spent} punti spesi oltre il budget {budget} ({draft.campaign_type})")
    race = catalogs.get_race(draft.race)
    if race is None:
        errors.append(f"razza sconosciuta: {draft.race}")
        return {"abilities": {}, "errors": errors}
    mods = race["mechanics"].get("ability_mods", {})
    final = dict(draft.abilities)
    if mods.get("any"):
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


def build_character(draft):
    """Costruisce la scheda lv1 completa (per ora: abilities, classe, skill).
    Ritorna dict con errors (bloccanti) e warnings."""
    abilities = apply_abilities(draft)
    errors = list(abilities["errors"])
    warnings = []
    final = abilities["abilities"]
    mods = {ab: ability_mod(sc) for ab, sc in final.items()} if final else {}
    cls = catalogs.get_class(draft.class_)
    sheet = {"name": draft.name, "race": draft.race, "class": draft.class_,
             "abilities": final, "errors": errors, "warnings": warnings}
    if errors:
        return sheet
    if cls is None:
        errors.append(f"classe sconosciuta: {draft.class_}")
        return sheet
    if draft.favored_class_bonus not in ("hp", "skill"):
        errors.append(f"favored_class_bonus non valido: {draft.favored_class_bonus} (atteso hp o skill)")
        return sheet
    mech = cls["mechanics"]
    lvl1 = mech["progression"][0]
    favored_hp = 1 if draft.favored_class_bonus == "hp" else 0
    sheet["hp"] = int(mech["hd"][1:]) + mods["con"] + favored_hp
    sheet["saves"] = {"fort": lvl1["fort"] + mods["con"],
                      "ref": lvl1["ref"] + mods["dex"],
                      "will": lvl1["will"] + mods["wis"]}
    sheet["bab"] = lvl1["bab"]
    sheet["initiative"] = mods["dex"]
    # skill
    budget = mech["skill_points_per_level"] + mods["int"] + (1 if draft.race == "Human" else 0)
    budget += 1 if draft.favored_class_bonus == "skill" else 0
    spent = sum(draft.skills.values())
    if spent > budget:
        errors.append(f"skill ranks: {spent} spesi oltre il budget {budget}")
    class_skills = mech.get("class_skills", [])
    out = {}
    for name, ranks in draft.skills.items():
        sk = catalogs.get_skill(name)
        if sk is None:
            errors.append(f"skill sconosciuta: {name}")
            continue
        if ranks != 1:
            errors.append(f"{name}: al lv1 ogni skill puo' avere al piu' 1 rank")
        key = sk["mechanics"]["key_ability"]
        is_class_skill = any(catalogs.class_skill_matches(name, cs) for cs in class_skills)
        class_bonus = 3 if ranks >= 1 and is_class_skill else 0
        if sk["mechanics"].get("trained_only") and not is_class_skill and ranks > 0:
            warnings.append(f"{name}: trained only e non di classe per {draft.class_}")
        out[name] = {"ranks": ranks, "ability": key,
                     "total": ranks + mods[key] + class_bonus, "class_skill": is_class_skill}
    sheet["skills"] = out
    validate_feats(draft, sheet)
    sheet["feats"] = list(draft.feats)
    return sheet
