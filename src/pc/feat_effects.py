"""Effetti meccanici dei talenti applicati ai valori della scheda (lv1).

La mappa e' deliberatamente dichiarativa: ogni talento -> dict di modificatori
applicati in apply_feat_effects. I talenti senza effetto numerico sui valori
lv1 (metamagic, granted di classe, condizionali) sono ignorati senza warning;
le selezioni mancanti/invalide producono warning (Task 2)."""

FEAT_EFFECTS = {
    "Toughness": {"hp": 3},
    "Dodge": {"ac": 1},
    "Iron Will": {"saves": {"will": 2}},
    "Lightning Reflexes": {"saves": {"ref": 2}},
    "Great Fortitude": {"saves": {"fort": 2}},
    "Improved Initiative": {"initiative": 4},
}


def apply_feat_effects(sheet):
    """Applica FEAT_EFFECTS ai talenti in sheet['feats'] (in place)."""
    for feat in sheet.get("feats", []):
        effect = FEAT_EFFECTS.get(feat)
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
