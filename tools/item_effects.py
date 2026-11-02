"""Effetti strutturati degli oggetti a slot dalle descrizioni AoN (E8-bis).

Solo bonus STATICI e TIPIZZATI, scritti nel vocabolario dei bersagli del
motore pathmaster (BonusTarget): "str", "save.will", "acNatural",
"skill.stealth"... Una frase che non si riconduce a un bersaglio noto
(condizionata, a scelta, sottotipo di abilita') non produce nulla: l'oggetto
resta selezionabile e il motore dichiara l'effetto non modellato. Il modello
locale puo' solo SEGNALARE frasi mancate; qui decidono i pattern.
"""

import re

ABILITIES = {
    "strength": "str",
    "dexterity": "dex",
    "constitution": "con",
    "intelligence": "int",
    "wisdom": "wis",
    "charisma": "cha",
}

TYPES = (
    "enhancement",
    "resistance",
    "deflection",
    "competence",
    "insight",
    "luck",
    "armor",
)

# Il tipo decide la componente della CA, come nel canale E8 di pathmaster:
# armatura su acArmor (non cumula con l'armatura indossata), il resto su ac.
_AC_BY_TYPE = {"armor": "acArmor"}

SAVES = ["save.fort", "save.ref", "save.will"]

# Il bersaglio e' la frase intera fino al primo terminatore: una coda in piu'
# ("...saving throws against disease") la rende sconosciuta, quindi scartata.
_FORM_A = re.compile(
    r"\+(\d+)\s+("
    + "|".join(TYPES)
    + r")\s+bonus\s+(?:on|to)\s+([A-Za-z ()'-]+?)\s*(?=[.,;]|\s+and\s|$)",
    re.IGNORECASE,
)

_PHRASES = {
    "all saving throws": SAVES,
    "saving throws": SAVES,
    "ac": ["ac"],
    "armor class": ["ac"],
    "natural armor": ["acNatural"],
}


# Gli id del motore (SKILL_IDS in pathmaster types.ts). Craft/Perform/
# Profession sono UNA abilita' nel motore: un sottotipo ("Perform (dance)")
# non ha bersaglio e resta fuori.
SKILLS = {
    "acrobatics",
    "appraise",
    "bluff",
    "climb",
    "craft",
    "diplomacy",
    "disable-device",
    "disguise",
    "escape-artist",
    "fly",
    "handle-animal",
    "heal",
    "intimidate",
    "knowledge-arcana",
    "knowledge-dungeoneering",
    "knowledge-engineering",
    "knowledge-geography",
    "knowledge-history",
    "knowledge-local",
    "knowledge-nature",
    "knowledge-nobility",
    "knowledge-planes",
    "knowledge-religion",
    "linguistics",
    "perception",
    "perform",
    "profession",
    "ride",
    "sense-motive",
    "sleight-of-hand",
    "spellcraft",
    "stealth",
    "survival",
    "swim",
    "use-magic-device",
}


def _skill(phrase):
    if not phrase.endswith((" checks", " check")):
        return None
    name = phrase.rsplit(" ", 1)[0]
    name = re.sub(r"knowledge \((\w+)\)", r"knowledge-\1", name)
    sid = name.replace(" ", "-")
    return f"skill.{sid}" if sid in SKILLS else None


def _targets(raw):
    # confronto ESATTO: una coda condizionata rende la frase sconosciuta
    phrase = raw.lower().strip()
    # "her Wisdom score", "the wearer's Strength score" = la caratteristica
    phrase = re.sub(r"^(?:her|his|its|their|the wearer['\u2019]s)\s+", "", phrase)
    phrase = re.sub(r"\s+score$", "", phrase)
    if phrase in ABILITIES:
        return [ABILITIES[phrase]]
    skill = _skill(phrase)
    if skill:
        return [skill]
    return _PHRASES.get(phrase, [])


# Forma "a varianti" delle voci AoN: "<tipo> bonus to <bersaglio> of +2, +4,
# or +6". Ogni valore elencato appartiene alla variante omonima ("+4").
_FORM_B = re.compile(
    r"("
    + "|".join(TYPES)
    + r")\s+bonus\s+(?:on|to)\s+([A-Za-z ()'-]+?)\s+of\s+((?:\+\d+(?:,?\s*or\s+|,\s*)?)+)",
    re.IGNORECASE,
)


def _variant_bonuses(text):
    """{valore: [bonus]} dalle frasi a varianti."""
    by_value = {}
    for btype, raw, values in _FORM_B.findall(text or ""):
        for value in re.findall(r"\+(\d+)", values):
            for target in _targets(raw):
                by_value.setdefault(int(value), []).append(
                    {"type": btype.lower(), "target": target, "value": int(value)}
                )
    return by_value


def extract_item_effects(entry):
    """Effetti per variante: [{"variant": "+4" | None, "bonuses": [...]}]."""
    text = entry.get("description") or ""
    fixed = extract_bonuses(text)
    variants = (entry.get("mechanics") or {}).get("variants") or []
    if not variants:
        # voce storica "Belt of Giant Strength +2" con testo a varianti:
        # vale il valore del +N nel nome
        own = re.search(r"\+(\d+)\s*$", entry.get("name") or "")
        if own:
            fixed = fixed + _variant_bonuses(text).get(int(own.group(1)), [])
        return [{"variant": None, "bonuses": fixed}] if fixed else []
    plus = [re.fullmatch(r"\+(\d+)", str(v).strip()) for v in variants]
    if not all(plus):
        # varianti con nome (Lesser/Greater, improved): il testo descrive di
        # solito la base, non ogni variante. Prima fetta: niente effetti.
        return []
    by_value = _variant_bonuses(text)
    out = []
    for variant, m in zip(variants, plus):
        extra = by_value.get(int(m.group(1)), [])
        if fixed or extra:
            out.append({"variant": variant, "bonuses": fixed + extra})
    return out


# Voci storiche del catalogo (256, una per variante): descrizione italiana,
# "bonus di <tipo> [di] +N a/al/alla <bersaglio>".
_IT_TYPES = {
    "resistenza": "resistance",
    "deviazione": "deflection",
    "miglioramento": "enhancement",
    "armatura": "armor",
    "competenza": "competence",
    "intuizione": "insight",
    "fortuna": "luck",
}
_IT_ABILITIES = {
    "forza": "str",
    "destrezza": "dex",
    "costituzione": "con",
    "intelligenza": "int",
    "saggezza": "wis",
    "carisma": "cha",
}
_IT_PHRASES = {
    "tutti i tiri salvezza": SAVES,
    "ca": ["ac"],
    "ca naturale": ["acNatural"],
}
_FORM_IT = re.compile(
    r"bonus\s+di\s+("
    + "|".join(_IT_TYPES)
    + r")\s+(?:di\s+)?\+(\d+)\s+(?:a|al|alla|ai|agli|alle)\s+([^.,;]+?)\s*(?=[.,;]|\s+e\s|$)",
    re.IGNORECASE,
)


def _it_targets(raw):
    phrase = re.sub(r"^punteggio\s+di\s+", "", raw.lower().strip())
    if phrase in _IT_ABILITIES:
        return [_IT_ABILITIES[phrase]]
    return _IT_PHRASES.get(phrase, [])


# Slot del corpo (Q7): niente armi/armature magiche (hanno il loro canale),
# niente artefatti e oggetti maledetti.
BODY_SLOTS = {
    "belt",
    "headband",
    "head",
    "neck",
    "shoulders",
    "ring",
    "wrists",
    "wrist",
    "hands",
    "feet",
    "eyes",
    "body",
    "chest",
}
_EXCLUDED_TAGS = {"artifact", "cursed"}


def _slot(entry):
    slot = (entry.get("mechanics") or {}).get("slot")
    if slot:
        return str(slot).lower()
    tags = [t[5:] for t in entry.get("tags") or [] if t.startswith("slot:")]
    return tags[0].lower() if tags else ""


def _attested(entry):
    """Attestata = ha una PAGINA oggetto AoN (...Display.aspx). Le voci
    storiche col solo link di ricerca (Search.aspx) sono doppioni italiani o
    nomi inventati: regola C9-S3, niente meccanica."""
    return any(
        "aonprd.com/" in u and "Display.aspx" in u
        for u in entry.get("reference_urls") or []
    )


def apply_effects(entries):
    """Scrive mechanics.effects sugli oggetti a slot del corpo. Idempotente:
    ricalcola da zero; una voce senza effetti estraibili resta intatta."""
    count = 0
    for entry in entries:
        if _slot(entry) not in BODY_SLOTS:
            continue
        if _EXCLUDED_TAGS & set(entry.get("tags") or []):
            continue
        if not _attested(entry):
            continue
        effects = extract_item_effects(entry)
        mechanics = entry.get("mechanics")
        if effects:
            entry.setdefault("mechanics", {})["effects"] = effects
            count += 1
        elif isinstance(mechanics, dict):
            mechanics.pop("effects", None)
    return count


# Una condizione PRIMA del bonus, nella stessa frase, lo rende condizionato
# ("When donned in forest terrain, ...", "If worn by an animal, ...",
# "Once per day ..."). Il solo indossare ("When worn,") non e' condizione.
_CONDITION = re.compile(
    r"\b(?:when|while|whenever|if|once|times per day|during|after|until|"
    r"as long as|aura|quando|mentre|se)\b"
    r"|\bin\s+(?:\w+\s+){0,3}(?:areas?|terrain|forests?|water|darkness|form)\b",
    re.IGNORECASE,
)
_JUST_WORN = re.compile(
    r"\b(?:when|while)\s+(?:worn|donned|wearing(?:\s+(?:it|them|this\s+\w+))?)\s*,",
    re.IGNORECASE,
)


# Un'attivazione nella frase PRIMA ("As a free action, the wearer can...
# This provides a +10 ...") condiziona il bonus che segue.
_ACTIVATION = re.compile(
    r"\b(?:as\s+an?\s+(?:free|standard|swift|move|immediate|full-round)\s+action|"
    r"(?:once|twice|\w+\s+times)\s+per\s+day|on\s+command|activat\w*)\b",
    re.IGNORECASE,
)


def _conditioned(text, start):
    sentence_start = max(text.rfind(".", 0, start), text.rfind(";", 0, start)) + 1
    prefix = _JUST_WORN.sub("", text[sentence_start:start])
    if _CONDITION.search(prefix):
        return True
    before = text[: max(sentence_start - 1, 0)]
    previous = re.split(r"[.;]\s*", before.strip())[-1] if before.strip() else ""
    return bool(_ACTIVATION.search(previous))


# Lista di abilita' chiusa da "checks": "on Acrobatics, Climb, and Stealth
# checks", "on Diplomacy and Sense Motive checks". Un nome ignoto nella lista
# ("Perform (oratory)") si scarta da solo, gli altri restano.
_SKILL_NAME = r"[A-Z][A-Za-z ()'-]*?"
_FORM_LIST = re.compile(
    r"\+(\d+)\s+("
    + "|".join(TYPES)
    + r")\s+bonus\s+on\s+((?:"
    + _SKILL_NAME
    + r",\s*)*"
    + _SKILL_NAME
    + r",?\s+and\s+"
    + _SKILL_NAME
    + r")\s+checks\s*(?=[.,;]|\s+and\s|$)"
)


def _list_bonuses(text):
    out = []
    for m in _FORM_LIST.finditer(text):
        if _conditioned(text, m.start()):
            continue
        names = re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(3))
        for name in names:
            skill = _skill(name.strip().lower() + " checks")
            if skill:
                out.append(
                    {
                        "type": m.group(2).lower(),
                        "target": skill,
                        "value": int(m.group(1)),
                    }
                )
    return out


_SAVE_IDS = {"fortitude": "save.fort", "reflex": "save.ref", "will": "save.will"}
_FORM_SAVES = re.compile(
    r"\+(\d+)\s+("
    + "|".join(TYPES)
    + r")\s+bonus\s+on\s+(Fortitude|Reflex|Will)(?:,?\s+and\s+(Fortitude|Reflex|Will))?"
    r"\s+(?:saves|saving\s+throws)\s*(?=[.,;]|\s+and\s|$)",
    re.IGNORECASE,
)


def _save_bonuses(text):
    out = []
    for m in _FORM_SAVES.finditer(text):
        if _conditioned(text, m.start()):
            continue
        for name in (m.group(3), m.group(4)):
            if name:
                out.append(
                    {
                        "type": m.group(2).lower(),
                        "target": _SAVE_IDS[name.lower()],
                        "value": int(m.group(1)),
                    }
                )
    return out


def extract_bonuses(text):
    out = _list_bonuses(text or "") + _save_bonuses(text or "")
    for it_type, value, raw in _FORM_IT.findall(text or ""):
        btype = _IT_TYPES[it_type.lower()]
        for target in _it_targets(raw):
            if target == "ac":
                target = _AC_BY_TYPE.get(btype, "ac")
            out.append({"type": btype, "target": target, "value": int(value)})
    for m in _FORM_A.finditer(text or ""):
        if _conditioned(text, m.start()):
            continue
        value, btype, raw = m.group(1), m.group(2).lower(), m.group(3)
        for target in _targets(raw):
            if target == "ac":
                target = _AC_BY_TYPE.get(btype, "ac")
            out.append({"type": btype, "target": target, "value": int(value)})
    return out


def main(argv=None):
    """python -m tools.item_effects [items.json] [--write]: senza --write
    stampa solo il conteggio. Formato del file invariato (indent 2, UTF-8,
    nessun a capo finale), scritto in byte per non convertire in CRLF."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/reference/ogl/items.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.path)
    data = json.loads(path.read_bytes().decode("utf-8"))
    count = apply_effects(data["entries"])
    print(f"oggetti con effetti: {count}")
    if args.write:
        path.write_bytes(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
