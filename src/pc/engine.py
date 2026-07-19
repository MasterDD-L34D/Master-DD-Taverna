"""Motore deterministico di creazione PG livelli 1-20 (nessun LLM)."""
import re

from src.pc import catalogs
from src.pc.feat_effects import apply_feat_effects

ABILS = ("str", "dex", "con", "int", "wis", "cha")


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
        return needed <= ctx["class_level"], f"richiede livello {needed} (personaggio lv{ctx['class_level']})"
    m = re.search(r"(\d+)(?:st|nd|rd|th)-level", text, re.I)
    if m:
        needed = int(m.group(1))
        return needed <= ctx["class_level"], f"richiede livello {needed} (personaggio lv{ctx['class_level']})"
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


def _norm_feat_name(name):
    """Normalizza per match case-insensitive: minuscole, punteggiatura -> spazi."""
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


# Alias tra capacita' di classe (classes.json special) e talenti feats.json
# quando il nome non coincide esattamente (chiavi gia' normalizzate).
SPECIAL_FEAT_ALIASES = {"unarmed strike": "Improved Unarmed Strike"}


def _granted_feats(draft):
    """Talenti concessi automaticamente dalla classe (le voci special di
    progression[0] che matchano un feat in feats.json, case-insensitive).
    Coprono solo i grant fissi del lv1 (es. Stunning Fist del Monk, Scribe
    Scroll del Wizard): i talenti bonus in scala sul livello sono conteggiati
    a parte da _class_bonus_feats. Non consumano slot e non richiedono
    prerequisiti."""
    cls = catalogs.get_class(draft.class_)
    if cls is None:
        return []
    index = {_norm_feat_name(f["name"]): f["name"] for f in catalogs.load("feats")}
    granted = []
    for special in cls["mechanics"]["progression"][0].get("special", []):
        norm = _norm_feat_name(special)
        feat_name = index.get(_norm_feat_name(SPECIAL_FEAT_ALIASES.get(norm, special)))
        if feat_name and feat_name not in granted:
            granted.append(feat_name)
    return granted


def _class_bonus_feats(class_name, level):
    """Talenti bonus da classe in scala sul livello (slot extra; i grant fissi
    del lv1 restano in _granted_feats): Fighter 1 + livello//2 (lv1 e ogni
    livello pari); Monk ai livelli 1, 2, 6, 10, 14, 18."""
    if class_name == "Fighter":
        return 1 + level // 2
    if class_name == "Monk":
        return sum(1 for x in (1, 2, 6, 10, 14, 18) if level >= x)
    return 0


def validate_feats(draft, sheet):
    """Conta talenti consentiti e valuta i prerequisiti noti.

    Il tetto scala col livello (1-20): 1 + livello//2 base, +1 se Human, + i
    talenti bonus di classe (_class_bonus_feats). I prerequisiti di livello
    ("fighter level 4th", "caster level 1st"...) sono valutati contro il
    livello del personaggio. I talenti concessi automaticamente dalla classe
    al lv1 (es. Improved Unarmed Strike e Stunning Fist per il Monk, Scribe
    Scroll per il Wizard) NON contano nel tetto consentito e NON passano il
    check dei prerequisiti."""
    granted = _granted_feats(draft)
    granted_norm = {_norm_feat_name(g) for g in granted}
    chosen = [f for f in draft.feats if _norm_feat_name(f) not in granted_norm]
    ctx = {"abilities": dict(sheet["abilities"]), "bab": sheet["bab"],
           "feats": chosen + granted, "skills": sheet.get("skills", {}),
           "class_level": draft.level}
    allowed = (1 + draft.level // 2 + (1 if draft.race == "Human" else 0)
               + _class_bonus_feats(draft.class_, draft.level))
    if len(chosen) > allowed:
        sheet["errors"].append(f"feat: {len(chosen)} selezionati su {allowed} consentiti al lv{draft.level}")
    for name in chosen:
        # Selezioni parentetiche: feats.json espande alcune voci ("Weapon Focus
        # (Longsword)") ma non altre ("Skill Focus (Perception)"): si prova il
        # nome intero e poi il nome base senza parentetica (come in _check_prereq).
        base = re.sub(r"\s*\([^)]*\)\s*$", "", name)
        feat = catalogs.find_feat(name) or catalogs.find_feat(base)
        if feat is None:
            sheet["errors"].append(f"talento sconosciuto: {name}")
            continue
        for prereq in feat.get("prerequisites", []):
            ok, note = _check_prereq(prereq, ctx)
            if not ok:
                sheet["errors"].append(f"{name}: prerequisito non soddisfatto ({note})")
            elif "non valutabile" in note:
                sheet["warnings"].append(f"{name}: {note}")
    sheet["feats"] = granted + chosen


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


def _signed(n):
    """'+3' per valori >= 0, '-2' altrimenti."""
    return f"{'+' if n >= 0 else ''}{n}"


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

    Applica il bonus di taglia: creature Small (es. Halfling, Gnome) hanno
    +1 alla CA e +1 a tutti i tiri per colpire.

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
    race = catalogs.get_race(draft.race)
    size_bonus = 1 if race and race["mechanics"].get("size") == "Small" else 0
    sheet["ac"] = 10 + armor + shield + dex + size_bonus
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
        attacks.append({"weapon": it["name"], "bonus": sheet["bab"] + mod + size_bonus,
                        "damage": dmg,
                        "critical": m.get("critical"), "range": m.get("range")})
    sheet["attacks"] = attacks


def apply_abilities(draft):
    """Valida point-buy e applica i modificatori razziali.
    Ritorna dict con 'abilities' finali, 'errors' e 'warnings'.
    race_bonus_ability passato per una razza senza bonus a scelta -> warning."""
    errors = []
    warnings = []
    if draft.method != "point-buy":
        errors.append(f"metodo non supportato: {draft.method} (solo point-buy)")
        return {"abilities": {}, "errors": errors, "warnings": warnings}
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
        return {"abilities": {}, "errors": errors, "warnings": warnings}
    spent = sum(catalogs.ability_cost(v) for v in draft.abilities.values())
    if spent > budget:
        errors.append(f"point-buy: {spent} punti spesi oltre il budget {budget} ({draft.campaign_type})")
    race = catalogs.get_race(draft.race)
    if race is None:
        errors.append(f"razza sconosciuta: {draft.race}")
        return {"abilities": {}, "errors": errors, "warnings": warnings}
    mods = race["mechanics"].get("ability_mods", {})
    if not mods.get("any") and draft.race_bonus_ability:
        warnings.append(f"race_bonus_ability ignorato per {draft.race} (nessun bonus a scelta)")
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
    return {"abilities": final, "errors": errors, "warnings": warnings}


def build_character(draft):
    """Costruisce la scheda completa al livello draft.level (1-20):
    abilities, classe, hp/saves/bab/special/spells da progression, skill,
    talenti, equip. Ritorna dict con errors (bloccanti) e warnings.

    Gli effetti meccanici dei talenti sono applicati ai valori calcolati come
    ultimo passo solo per i talenti supportati in src/pc/feat_effects.py
    (passivi lv1, Weapon/Skill Focus, Weapon Finesse); gli altri sono solo
    validati (prerequisiti e conteggio)."""
    abilities = apply_abilities(draft)
    errors = list(abilities["errors"])
    warnings = list(abilities.get("warnings", []))
    final = abilities["abilities"]
    mods = {ab: ability_mod(sc) for ab, sc in final.items()} if final else {}
    cls = catalogs.get_class(draft.class_)
    sheet = {"name": draft.name, "race": draft.race, "class": draft.class_,
             "level": draft.level, "abilities": final,
             "errors": errors, "warnings": warnings}
    if errors:
        return sheet
    if cls is None:
        errors.append(f"classe sconosciuta: {draft.class_}")
        return sheet
    if type(draft.level) is not int or not 1 <= draft.level <= 20:
        errors.append(f"level: deve essere un intero 1-20 (ricevuto {draft.level!r})")
        return sheet
    if draft.hp_method not in ("average", "max"):
        errors.append(f"hp_method non valido: {draft.hp_method}")
        return sheet
    if draft.favored_class_bonus not in ("hp", "skill"):
        errors.append(f"favored_class_bonus non valido: {draft.favored_class_bonus} (atteso hp o skill)")
        return sheet
    mech = cls["mechanics"]
    lvl = mech["progression"][draft.level - 1]
    hd = int(mech["hd"][1:])
    per_level = hd if draft.hp_method == "max" else hd // 2 + 1
    favored_hp = draft.level if draft.favored_class_bonus == "hp" else 0
    sheet["hp"] = hd + (draft.level - 1) * per_level + mods["con"] * draft.level + favored_hp
    sheet["saves"] = {"fort": lvl["fort"] + mods["con"],
                      "ref": lvl["ref"] + mods["dex"],
                      "will": lvl["will"] + mods["wis"]}
    sheet["bab"] = lvl["bab"]
    sheet["special"] = list(lvl.get("special", []))
    if lvl.get("spells_per_day"):
        sheet["spells_per_day"] = dict(lvl["spells_per_day"])
    if lvl.get("extra_progression"):
        sheet["extra_progression"] = dict(lvl["extra_progression"])
    sheet["initiative"] = mods["dex"]
    # skill: il minimo RAW da classe+Int e' 1 per livello; i bonus Human/favored
    # si sommano dopo (sempre per livello); ranks max per skill = livello
    budget = max(mech["skill_points_per_level"] + mods["int"], 1) * draft.level
    budget += draft.level if draft.race == "Human" else 0
    budget += draft.level if draft.favored_class_bonus == "skill" else 0
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
        if not 0 < ranks <= draft.level:
            errors.append(f"{name}: {ranks} ranks non validi (1..{draft.level} al lv{draft.level})")
        key = sk["mechanics"]["key_ability"]
        is_class_skill = any(catalogs.class_skill_matches(name, cs) for cs in class_skills)
        class_bonus = 3 if ranks >= 1 and is_class_skill else 0
        if sk["mechanics"].get("trained_only") and not is_class_skill and ranks > 0:
            warnings.append(f"{name}: trained only e non di classe per {draft.class_}")
        out[name] = {"ranks": ranks, "ability": key,
                     "total": ranks + mods[key] + class_bonus, "class_skill": is_class_skill}
    sheet["skills"] = out
    validate_feats(draft, sheet)
    apply_equipment(draft, sheet)
    validate_traits(draft, sheet)
    apply_feat_effects(sheet)
    return sheet


def render_markdown(sheet):
    """Scheda testuale compatta della build."""
    if sheet.get("errors"):
        return "# Errori di validazione\n" + "\n".join(sheet["errors"]) + "\n"
    mods = {ab: ability_mod(sc) for ab, sc in sheet["abilities"].items()}
    lines = [f"# {sheet['name']}",
             f"{sheet['race']} {sheet['class']} {sheet.get('level', 1)} — PF: {sheet['hp']} — CA: {sheet['ac']} — Iniziativa: {_signed(sheet['initiative'])}",
             "",
             "**Caratteristiche**: " + ", ".join(
                 f"{ab.upper()} {sc} ({_signed(mods[ab])})"
                 for ab, sc in sheet["abilities"].items()),
             f"**TS**: Tempra {_signed(sheet['saves']['fort'])}, "
             f"Riflessi {_signed(sheet['saves']['ref'])}, "
             f"Volonta' {_signed(sheet['saves']['will'])} — BAB +{sheet['bab']}"]
    if sheet.get("attacks"):
        lines.append("**Attacchi**: " + "; ".join(f"{a['weapon']} {_signed(a['bonus'])} ({a['damage']})" for a in sheet["attacks"]))
    if sheet.get("skills"):
        lines.append("**Skill**: " + ", ".join(f"{n} {_signed(s['total'])}" for n, s in sheet["skills"].items()))
    if sheet.get("feats"):
        lines.append("**Talenti**: " + ", ".join(sheet["feats"]))
    if sheet.get("traits"):
        lines.append("**Tratti**: " + ", ".join(sheet["traits"]))
    if sheet.get("equipment"):
        lines.append(f"**Equip** (oro restante {sheet.get('gold_remaining', 0):.2f} gp): "
                     + ", ".join(i["name"] for i in sheet["equipment"]))
    if sheet.get("warnings"):
        lines.append("_Note_: " + " | ".join(sheet["warnings"]))
    return "\n".join(lines) + "\n"
