"""Motore deterministico di creazione PG lv1 (nessun LLM)."""
import re

from src.pc import catalogs

ABILS = ("str", "dex", "con", "int", "wis", "cha")

FEAT_BONUS_CLASSES = {"Fighter", "Monk"}


def _check_prereq(prereq, ctx):
    """Valuta un prerequisito testuale. Ritorna (ok, nota)."""
    text = prereq.rstrip(".")
    m = re.match(r"^(Str|Dex|Con|Int|Wis|Cha)\w*\s+(\d+)$", text, re.I)
    if m:
        ab = m.group(1)[:3].lower()
        need = int(m.group(2))
        return ctx["abilities"][ab] >= need, f"richiede {m.group(1)} {need}"
    m = re.match(r"^base attack bonus \+(\d+)$", text, re.I)
    if m:
        return ctx["bab"] >= int(m.group(1)), f"richiede BAB +{m.group(1)}"
    base = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    for candidate in (text, base):
        if catalogs.find_feat(candidate) is not None:
            return candidate in ctx["feats"], f"richiede il talento {text}"
    m = re.search(r"level\s+(\d+)(?:st|nd|rd|th)", text, re.I)
    if m:
        needed = int(m.group(1))
        return needed <= 1, f"richiede livello {needed} (personaggio lv1)"
    m = re.search(r"(\d+)(?:st|nd|rd|th)-level", text, re.I)
    if m:
        needed = int(m.group(1))
        return needed <= 1, f"richiede livello {needed} (personaggio lv1)"
    if "proficien" in text.lower():
        return True, f"proficiency: {text} (assunta da classe)"
    m = re.search(r"(\d+)\s+ranks?", text, re.I)
    if m:
        n = int(m.group(1))
        if n > 1:
            return False, f"richiede {n} ranks (personaggio lv1) ({text})"
        skill_ref = re.sub(r"\s*\d+\s+ranks?.*$", "", text, flags=re.I).strip(" ,;")
        if skill_ref and skill_ref not in ctx.get("skills", {}):
            return False, f"richiede 1 rank in {skill_ref} (non presente nel draft)"
        return True, f"1 rank: {text}"
    if re.search(r"rank", text, re.I):
        return True, f"skill rank: {text} (forma non verificabile, accettata al lv1)"
    return True, f"forma prerequisito non valutabile: {text}"  # warning, non errore


def validate_feats(draft, sheet):
    """Conta talenti consentiti e valuta i prerequisiti noti."""
    ctx = {"abilities": dict(sheet["abilities"]), "bab": sheet["bab"],
           "feats": list(draft.feats), "skills": sheet.get("skills", {})}
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


def validate_traits(draft, sheet):
    if len(draft.traits) > 2:
        sheet["errors"].append(f"tratti: {len(draft.traits)} selezionati, max 2")
    seen = set()
    out = []
    for name in draft.traits:
        trait = catalogs.find_trait(name)
        if trait is None:
            sheet["errors"].append(f"tratto sconosciuto: {name}")
            continue
        cat = trait["mechanics"].get("category")
        if cat in seen:
            sheet["errors"].append(f"tratti: due tratti della stessa categoria ({cat})")
        seen.add(cat)
        out.append(name)
    sheet["traits"] = out


def ability_mod(score):
    return (score - 10) // 2


def _parse_cost(text):
    """'15 gp' -> 15 (int); '5 sp' -> 0.5; '1 cp' -> 0.01 (float, 2 decimali)."""
    m = re.search(r"(\d[\d,]*)\s*(gp|sp|cp)", str(text or ""))
    if not m:
        return 0
    value = int(m.group(1).replace(",", ""))
    if m.group(2) == "gp":
        return value
    return round(value / (10 if m.group(2) == "sp" else 100), 2)


def _parse_bonus(text):
    """'+4' -> 4; None/''/'-' -> 0."""
    m = re.match(r"^\+(\d+)$", str(text or ""))
    return int(m.group(1)) if m else 0


def _range_ft(text):
    """'60 ft.' -> 60; None/'' -> 0."""
    m = re.search(r"(\d+)\s*ft", str(text or ""))
    return int(m.group(1)) if m else 0


def apply_equipment(draft, sheet):
    """Valida gli acquisti contro la ricchezza iniziale e calcola CA/attacchi.

    Limitazione nota: classificazione ranged per euristica sulla gittata
    (ranged solo se range >= 30 ft) — armi da tiro con gittata < 30 ft
    classificate melee; le armi da lancio (Dagger, Club, Shortspear...)
    restano correttamente melee."""
    cls = catalogs.get_class(draft.class_)
    wealth_text = cls["mechanics"].get("starting_wealth", "")
    if "average" in wealth_text:
        m = re.search(r"average\s+([\d,]+)\s*gp", wealth_text)
        wealth = int(m.group(1).replace(",", "")) if m else 0
    else:
        wealth = _parse_cost(wealth_text)
    spent = 0
    items = []
    for name in draft.equipment:
        item = catalogs.find_equipment(name)
        if item is None:
            sheet["errors"].append(f"equipaggiamento sconosciuto: {name}")
            continue
        cost = _parse_cost(item["mechanics"].get("cost"))
        spent += cost
        items.append({"name": name, "cost": cost, "mechanics": item["mechanics"],
                      "tags": item.get("tags", [])})
    spent = round(spent, 2)
    if spent > wealth:
        sheet["errors"].append(
            f"wealth: spesi {spent:.2f} gp oltre la ricchezza iniziale {wealth:.2f} gp")
    sheet["gold_remaining"] = round(wealth - spent, 2)
    sheet["equipment"] = items
    mods = {ab: ability_mod(sc) for ab, sc in sheet["abilities"].items()}
    armors = []
    shield = 0
    caps = []
    for it in items:
        m = it["mechanics"]
        bonus = _parse_bonus(m.get("armor_bonus"))
        md = m.get("maximum_dex_bonus") or m.get("max_dex_bonus")
        if "shield" in it["tags"]:
            shield += bonus
            if md:
                caps.append(_parse_bonus(md))
        elif bonus:
            armors.append((bonus, _parse_bonus(md) if md else None))
    armor = 0
    if len(armors) > 1:
        sheet["errors"].append("indossabili piu' armature: usa la migliore")
    if armors:
        best = max(armors, key=lambda a: a[0])
        armor = best[0]
        if best[1] is not None:
            caps.append(best[1])
    max_dex = min(caps) if caps else None
    dex = min(mods["dex"], max_dex) if max_dex is not None else mods["dex"]
    sheet["ac"] = 10 + armor + shield + dex
    attacks = []
    for it in items:
        if "weapon" not in it["tags"]:
            continue
        m = it["mechanics"]
        is_ranged = _range_ft(m.get("range")) >= 30
        mod = mods["dex"] if is_ranged else mods["str"]
        dmg = m.get("dmg_m", "-")
        if not is_ranged and mod != 0:
            dmg = f"{dmg}{'+' if mod > 0 else ''}{mod}"
        attacks.append({"weapon": it["name"], "bonus": sheet["bab"] + mod,
                        "damage": dmg,
                        "critical": m.get("critical"), "range": m.get("range")})
    sheet["attacks"] = attacks


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
    """Costruisce la scheda lv1 completa (abilities, classe, skill, talenti, equip).
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
    apply_equipment(draft, sheet)
    validate_traits(draft, sheet)
    return sheet


def render_markdown(sheet):
    """Scheda testuale compatta della build lv1."""
    mods = {ab: ability_mod(sc) for ab, sc in sheet["abilities"].items()}
    lines = [f"# {sheet['name']}",
             f"{sheet['race']} {sheet['class']} 1 — PF: {sheet['hp']} — CA: {sheet['ac']} — Iniziativa: {'+' if sheet['initiative'] >= 0 else ''}{sheet['initiative']}",
             "",
             "**Caratteristiche**: " + ", ".join(
                 f"{ab.upper()} {sc} ({'+' if mods[ab] >= 0 else ''}{mods[ab]})"
                 for ab, sc in sheet["abilities"].items()),
             f"**TS**: Tempra {'+' if sheet['saves']['fort'] >= 0 else ''}{sheet['saves']['fort']}, "
             f"Riflessi {'+' if sheet['saves']['ref'] >= 0 else ''}{sheet['saves']['ref']}, "
             f"Volonta' {'+' if sheet['saves']['will'] >= 0 else ''}{sheet['saves']['will']} — BAB +{sheet['bab']}"]
    if sheet.get("attacks"):
        lines.append("**Attacchi**: " + "; ".join(f"{a['weapon']} +{a['bonus']} ({a['damage']})" for a in sheet["attacks"]))
    if sheet.get("skills"):
        lines.append("**Skill**: " + ", ".join(f"{n} +{s['total']}" for n, s in sheet["skills"].items()))
    if sheet.get("feats"):
        lines.append("**Talenti**: " + ", ".join(sheet["feats"]))
    if sheet.get("traits"):
        lines.append("**Tratti**: " + ", ".join(sheet["traits"]))
    if sheet.get("equipment"):
        lines.append(f"**Equip** (oro restante {sheet.get('gold_remaining', 0)} gp): "
                     + ", ".join(i["name"] for i in sheet["equipment"]))
    if sheet.get("warnings"):
        lines.append("_Note_: " + " | ".join(sheet["warnings"]))
    return "\n".join(lines) + "\n"
