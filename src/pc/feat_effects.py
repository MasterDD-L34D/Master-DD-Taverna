"""Effetti meccanici dei talenti applicati ai valori della scheda (lv1).

La mappa e' deliberatamente dichiarativa: ogni talento -> dict di modificatori
applicati in apply_feat_effects. I talenti senza effetto numerico sui valori
lv1 (metamagic, granted di classe, condizionali) sono ignorati senza warning;
le selezioni mancanti/invalide producono warning."""
import re

from src.pc import catalogs

FEAT_EFFECTS = {
    "Toughness": {"hp": 3},
    "Dodge": {"ac": 1},
    "Iron Will": {"saves": {"will": 2}},
    "Lightning Reflexes": {"saves": {"ref": 2}},
    "Great Fortitude": {"saves": {"fort": 2}},
    "Improved Initiative": {"initiative": 4},
}


def parse_selection(feat_name):
    """'Weapon Focus (Longsword)' -> ('Weapon Focus', 'Longsword'); altro -> (name, None)."""
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", feat_name)
    return (m.group(1).strip(), m.group(2).strip()) if m else (feat_name, None)


def _apply_weapon_focus(sheet, selection):
    if not sheet.get("attacks"):
        sheet["warnings"].append("Weapon Focus: nessun attacco da migliorare")
        return
    if selection:
        for attack in sheet["attacks"]:
            if attack["weapon"].lower() == selection.lower():
                attack["bonus"] += 1
                return
        sheet["warnings"].append(f"Weapon Focus ({selection}): arma non in equip, nessun bonus")
        return
    sheet["attacks"][0]["bonus"] += 1
    sheet["warnings"].append("Weapon Focus senza selezione: bonus applicato alla prima arma")


def _apply_skill_focus(sheet, selection, mods):
    if not selection:
        sheet["warnings"].append("Skill Focus senza selezione: nessun bonus applicato")
        return
    skills = sheet.setdefault("skills", {})
    if selection in skills:
        skills[selection]["total"] += 3
        return
    sk = catalogs.get_skill(selection)
    if sk is None:
        sheet["warnings"].append(f"Skill Focus ({selection}): skill sconosciuta")
        return
    key = sk["mechanics"]["key_ability"]
    skills[selection] = {"ranks": 0, "ability": key, "total": mods[key] + 3, "class_skill": False}


# Lista curata v1 di armi finessabili comuni (la categoria "light" completa
# non e' ancora nei mechanics del catalogo equipment; ampliare quando disponibile).
FINESSE_WEAPONS = {
    "Dagger", "Punching dagger", "Rapier", "Short sword", "Whip",
    "Spiked chain", "Elven curve blade", "Light hammer", "Handaxe",
    "Sickle", "Kukri", "Starknife",
    "Light mace", "Gauntlet", "Spiked gauntlet", "Throwing axe",
}


def _apply_finesse(sheet, mods):
    """Weapon Finesse: sulle armi finessabili il tiro per colpire usa Dex al
    posto di Str (apply_equipment ha gia' messo Str per melee / Dex per ranged),
    ma solo se migliorativo (RAW "may use Dex": con Str >= Dex resta Str).
    Il danno resta a Str (RAW: finesse cambia solo il tiro per colpire)."""
    for attack in sheet.get("attacks", []):
        if attack["weapon"] in FINESSE_WEAPONS and mods["dex"] > mods["str"]:
            attack["bonus"] += mods["dex"] - mods["str"]


def apply_feat_effects(sheet):
    """Applica FEAT_EFFECTS ai talenti in sheet['feats'] (in place).

    No-op sulle schede con errori: una scheda invalida non riceve bonus.
    Weapon Focus (X) e Skill Focus (Y) hanno effetto dipendente dalla
    selezione parentetica; la selezione mancante/invalida produce warning.
    Weapon Finesse sostituisce Str con Dex al tiro per colpire delle armi
    in FINESSE_WEAPONS, solo quando migliorativo."""
    if sheet.get("errors"):
        return
    mods = {ab: (sc - 10) // 2 for ab, sc in sheet["abilities"].items()}
    for feat in sheet.get("feats", []):
        base, selection = parse_selection(feat)
        if base == "Weapon Focus":
            _apply_weapon_focus(sheet, selection)
            continue
        if base == "Skill Focus":
            _apply_skill_focus(sheet, selection, mods)
            continue
        if base == "Weapon Finesse":
            _apply_finesse(sheet, mods)
            continue
        effect = FEAT_EFFECTS.get(base)
        if not effect:
            continue
        if "hp" in effect:
            sheet["hp"] += effect["hp"]
        if "ac" in effect:
            sheet["ac"] += effect["ac"]
        if "initiative" in effect:
            sheet["initiative"] += effect["initiative"]
        for save, bonus in effect.get("saves", {}).items():
            sheet["saves"][save] += bonus
