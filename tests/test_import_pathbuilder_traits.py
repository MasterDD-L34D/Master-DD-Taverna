"""Test per tools/import_pathbuilder_traits.py — background traits PB (C1).

C1 (ciclo Builder E2E, gap report B1: 126 trait mancanti / 124 build):
import di `data_background_traits.xml` (1.569 voci; dataset PI local-only in
`data/reference/pi_local_only/pathbuilder/`, MAI committato) verso UN JSON
committato in pathmaster-dd src/data/: pathbuilder-background-traits.json —
solo NOME + CATEGORIA per voce.

Forma reale del file (ricognizione 2026-08-08): <Root><Row>; ogni riga ha
<Name>, <Type> (codice numerico di categoria), <Ref> (URL d20pfsrd, mai
esportata), <Description> (testo PI, MAI esportata), talvolta <Source> e
campi <r*>.

La mappa codice->categoria e' ESPLICITA e dichiarata, cross-checkata sui
path dei <Ref> (traits/combat-traits, traits/faith-traits, traits/drawbacks,
...): 0 Combat, 1 Faith, 2 Magic, 3 Social, 4 Campaign, 5 Equipment,
6 Faction, 7 Race, 8 Regional, 9 Religion, 10 Drawback, 11 Exemplar.

Policy OGL: il JSON committato non include MAI <Description> (testo Paizo
PI) ne' <Ref>: solo nome + categoria.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import import_pathbuilder_traits as pb

XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<Row>
\t\t<Name>Reactionary</Name>
\t\t<Type>0</Type>
\t\t<Ref>http://www.d20pfsrd.com/traits/combat-traits/reactionary</Ref>
\t\t<Description>You were bullied often as a child...</Description>
\t</Row>
\t<Row>
\t\t<Name>Fate&#8217;s Favored</Name>
\t\t<Type>1</Type>
\t\t<Ref>http://www.d20pfsrd.com/traits/faith-traits/fate-s-favored</Ref>
\t\t<Description>The fates watch over you.</Description>
\t</Row>
\t<Row>
\t\t<Name>Umbral Unmasking</Name>
\t\t<Type>10</Type>
\t\t<Ref>http://www.d20pfsrd.com/traits/drawbacks/umbral-unmasking</Ref>
\t\t<Description>You cast no shadow.</Description>
\t</Row>
</Root>
"""


def test_parse_estrae_nome_e_categoria_dal_type_code():
    entries, dup = pb.parse_traits_xml(XML)
    assert dup == []
    assert entries == [
        {"name": "Reactionary", "category": "Combat"},
        {"name": "Fate’s Favored", "category": "Faith"},
        {"name": "Umbral Unmasking", "category": "Drawback"},
    ]


def test_mai_description_ne_ref_nel_dato_esportato():
    entries, _ = pb.parse_traits_xml(XML)
    for e in entries:
        assert set(e.keys()) == {"name", "category"}


def test_type_code_sconosciuto_esplode_dichiarato():
    xml = XML.replace("<Type>0</Type>", "<Type>42</Type>")
    try:
        pb.parse_traits_xml(xml)
    except ValueError as e:
        assert "42" in str(e)
    else:
        raise AssertionError("Type sconosciuto accettato in silenzio")


def test_nomi_duplicati_dichiarati_non_fusi():
    xml = XML + ""
    xml = xml.replace("</Root>", "")
    xml += """
\t<Row>
\t\t<Name>Reactionary</Name>
\t\t<Type>3</Type>
\t\t<Ref>http://www.d20pfsrd.com/traits/social-traits/reactionary</Ref>
\t\t<Description>Altro tratto omonimo.</Description>
\t</Row>
</Root>
"""
    entries, dup = pb.parse_traits_xml(xml)
    # Entrambe le voci restano (mai merge silenzioso); il duplicato e' NOMINATO.
    assert len(entries) == 4
    assert dup == ["Reactionary"]


def test_mappa_categorie_completa_e_onesta():
    # I 12 codici attestati nel dataset reale (ricognizione 2026-08-08).
    assert pb.TYPE_CATEGORY == {
        0: "Combat",
        1: "Faith",
        2: "Magic",
        3: "Social",
        4: "Campaign",
        5: "Equipment",
        6: "Faction",
        7: "Race",
        8: "Regional",
        9: "Religion",
        10: "Drawback",
        11: "Exemplar",
    }
