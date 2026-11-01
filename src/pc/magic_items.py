"""Effetti RAW minimi degli oggetti magici usati dal banco build."""

import re

_ABILITY_ITEMS = (
    (re.compile(r"belt of giant strength \+([246])", re.I), "str"),
    (re.compile(r"belt of incredible dexterity \+([246])", re.I), "dex"),
    (re.compile(r"belt of mighty constitution \+([246])", re.I), "con"),
    (re.compile(r"headband of inspired wisdom \+([246])", re.I), "wis"),
    (re.compile(r"headband of alluring charisma \+([246])", re.I), "cha"),
)


def parse_magic_item(name):
    """Restituisce un effetto strutturato, oppure None se il nome e' ignoto."""
    text = str(name).strip()
    match = re.fullmatch(
        r"headband of vast intelligence \+([246])(?:\s*\((.*)\))?", text, re.I
    )
    if match:
        return {
            "ability": "int",
            "enhancement": int(match.group(1)),
            "granted_skills": [
                s.strip() for s in (match.group(2) or "").split(";") if s.strip()
            ],
        }
    for pattern, ability in _ABILITY_ITEMS:
        match = pattern.fullmatch(text)
        if match:
            return {"ability": ability, "enhancement": int(match.group(1))}
    match = re.fullmatch(r"cloak of resistance \+([1-5])", text, re.I)
    if match:
        return {"resistance": int(match.group(1))}
    match = re.fullmatch(r"bracers of armor \+([1-8])", text, re.I)
    if match:
        return {"armor": int(match.group(1))}
    match = re.fullmatch(r"ring of protection \+([1-5])", text, re.I)
    if match:
        return {"deflection": int(match.group(1))}
    if text.casefold() == "dusty rose prism ioun stone":
        return {"insight_ac": 1}
    return None
