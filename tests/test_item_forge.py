"""Test per tools/item_forge.py — core deterministico oggetti magici PF1e.
Riferimenti ufficiali dal legacy Item-generator (Formato Torneo)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.item_forge import (
    aura_for_cl,
    crafting_cost,
    forge_from_spell,
    min_caster_level,
    price_bonus_item,
    price_charged_item,
    price_spell_item,
    rarity_for_price,
    save_dc,
    school_it,
    spell_lookup,
)


class TestPriceSpellItem:
    def test_fireball_1_day(self):
        # fireball (3) x LI 5 x 1800 = 27.000 gp
        assert price_spell_item(3, 5, "1/day") == 27_000

    def test_fireball_3_day(self):
        assert price_spell_item(3, 5, "3/day") == 81_000

    def test_unlimited(self):
        # shield (1) x LI 1 x 8000 = 8.000 gp
        assert price_spell_item(1, 1, "unlimited") == 8_000

    def test_cl_sotto_minimo_errore_onesto(self):
        with pytest.raises(ValueError, match="sotto il minimo RAW"):
            price_spell_item(3, 4, "1/day")  # fireball vuole LI 5

    def test_uses_sconosciuto(self):
        with pytest.raises(ValueError, match="uses non ammesso"):
            price_spell_item(1, 1, "5/day")


class TestChargedItem:
    def test_wand_of_fireball_cl5(self):
        # Riferimento legacy: 11.250 gp (3 x 5 x 750)
        assert price_charged_item(3, 5, "wand") == 11_250

    def test_staff(self):
        assert price_charged_item(3, 5, "staff") == 6_000

    def test_kind_sconosciuto(self):
        with pytest.raises(ValueError, match="kind non ammesso"):
            price_charged_item(1, 1, "rod")


class TestBonusItem:
    def test_ring_of_protection(self):
        # Riferimento ufficiale: +1 deviazione = 2.000 gp
        assert price_bonus_item(1, "deviazione") == 2_000

    def test_cloak_of_resistance(self):
        # Riferimento ufficiale: +1 resistenza = 1.000 gp
        assert price_bonus_item(1, "resistenza") == 1_000

    def test_arma_piu_due(self):
        # +2 potenziamento = 4 x 2000 = 8.000 gp
        assert price_bonus_item(2, "potenziamento") == 8_000

    def test_tipo_sconosciuto(self):
        with pytest.raises(ValueError, match="bonus_type sconosciuto"):
            price_bonus_item(1, "insight")

    def test_bonus_zero(self):
        with pytest.raises(ValueError, match=">= 1"):
            price_bonus_item(0, "competenza")


class TestDerived:
    def test_min_cl(self):
        assert min_caster_level(3) == 5
        assert min_caster_level(9) == 17
        with pytest.raises(ValueError):
            min_caster_level(0)

    def test_crafting_cost(self):
        assert crafting_cost(27_001) == 13_500
        assert crafting_cost(2_000) == 1_000

    def test_aura(self):
        assert aura_for_cl(1) == "Debole"
        assert aura_for_cl(5) == "Debole"
        assert aura_for_cl(6) == "Moderata"
        assert aura_for_cl(11) == "Moderata"
        assert aura_for_cl(12) == "Forte"
        assert aura_for_cl(20) == "Forte"

    def test_save_dc(self):
        assert save_dc(3) == 16  # 10+3+3 (min +3)
        assert save_dc(3, 5) == 18
        assert save_dc(1, 0) == 14  # mod sotto il minimo -> +3

    def test_rarity(self):
        assert rarity_for_price(9_999) == "Comune"
        assert rarity_for_price(10_000) == "Non comune"
        assert rarity_for_price(50_001) == "Raro"
        assert rarity_for_price(200_001) == "Unico"

    def test_school_it(self):
        assert school_it("Evocation") == "Invocazione"
        assert school_it("abjuration") == "Abjurazione"
        with pytest.raises(ValueError, match="scuola sconosciuta"):
            school_it("Chronomancy")


class TestSpellLookup:
    def test_lookup_esatto_e_case_insensitive(self):
        e = spell_lookup("  FIREBALL ")
        assert e["name"] == "Fireball"

    def test_lookup_mancante_errore_onesto(self):
        with pytest.raises(KeyError, match="non trovato nel catalogo"):
            spell_lookup("Palla di Fuoco")


class TestForgeFromSpell:
    def test_blocco_deterministico_fireball(self):
        out = forge_from_spell("fireball", 5, "1/day")
        assert out["spell"] == "Fireball"
        assert out["spell_level"] == 3 and out["caster_level"] == 5
        assert out["price"] == 27_000 and out["crafting_cost"] == 13_500
        assert out["aura"] == "Debole"
        assert out["school_it"] == "Invocazione"
        assert out["rarity"] == "Non comune"
        assert out["saving_throw"].startswith("CD ")
        assert out["spell_resistance"] == "Sì"

    def test_cl_sotto_minimo(self):
        with pytest.raises(ValueError, match="sotto il minimo RAW"):
            forge_from_spell("fireball", 3)
