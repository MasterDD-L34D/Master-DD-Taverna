# Cantiere generatore: armatura inventata per classi non competenti

Data: 2026-10-20
Origine: audit P12 del corpus in `tooling/pathmaster-dd` (sonda D3): 27 build
con armatura stimata non competente, di cui le 6 `wizard_elf_universalist*`
con `query_params.stub: True` generate dallo stub di questo repo.

## Difetto

In `src/builder/stub_builder.py`, il fallback finale della sezione equip
(classi senza progressione dedicata wizard-evoker/cutpurse) inseriva sempre:

```python
equip_full.extend(["Arma preferita", "Armatura leggera"])
```

quindi anche per classi che secondo i testi di classe PF1 (sezione
"Weapon and Armor Proficiency" di ciascuna classe) non sono competenti in
alcuna armatura: wizard e sorcerer (CRB), witch (APG), arcanist (ACG),
monk (CRB), psychic (Occult Adventures).

Il review a valle del generatore (`src/data/build_index.json` /
`build_review.json`) flaggava gia' il sintomo:
"Prerequisiti catalogo non soddisfatti: Armatura di cuoio borchiato:
Light armor proficiency". Il difetto era quindi noto a valle ma non
corretto a monte.

## Fix

Il fallback ora inserisce "Armatura leggera" solo se la classe non e'
nell'insieme `classi_senza_armatura` (wizard, sorcerer, witch, arcanist,
monk, psychic). Il resto del comportamento e' invariato.

## Limite dichiarato

- L'insieme copre le classi del corpus; una classe non elencata (o
  sconosciuta) riceve ancora la riga generica "Armatura leggera" come
  prima del fix.
- Il fallback CA (stesso file, blocco `ac_block`) inventa ancora una
  componente `armatura: 5` nella CA quando manca lo snapshot: limite noto,
  non toccato in questo cantiere.
- Il corpus NON e' stato rigenerato (decisione D4: la fotografia resta
  quella dell'audit). Le 6 build wizard del corpus conservano quindi
  l'equipaggiamento stimato precedente finche' il corpus non viene
  rigenerato.

## Verifica

- Test manuali del payload stub: wizard/sorcerer/witch/arcanist/monk/psychic
  -> equip `["Arma preferita"]`; fighter/cleric/classe sconosciuta ->
  `["Arma preferita", "Armatura leggera"]` (invariato).
- 9 test nuovi in `tests/test_app.py`
  (`test_build_stub_no_light_armor_for_unproficient_classes`, parametrizzato
  sulle 6 classi; `test_build_stub_keeps_light_armor_for_other_classes`,
  parametrizzato su fighter/cleric/unknownclass a pinzare il limite
  dichiarato).
- Suite completa: 83 passed (74 prima del cantiere + 9 nuovi), 0 failure.
