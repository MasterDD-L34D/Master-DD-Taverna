"""Test per tools/import_pcgen_class_skills.py -- le abilita' di classe (CSKILL).

Fixture LST inline (MAI rete), forma reale ricostruita sui file veri al commit
PCGen 70057897.

Il caso che questo file esiste per fissare: nelle abilita' che concedono le
abilita' di classe il NOME VISUALIZZATO e' letteralmente "Class Skills" per
tutte, e la classe sta nella `KEY:`. Raggruppare per nome da' UNA voce per
l'intero gioco -- misurato mentre si scriveva l'estrattore.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_la_classe_viene_dalla_KEY_non_dal_nome_visualizzato():
    from tools import import_pcgen_class_skills as pcs

    # Riga reale (apg_abilities_class.lst): il nome e' "Class Skills", la
    # classe sta nella KEY. Se l'estrattore guardasse il nome, tutte le classi
    # collasserebbero su una voce sola chiamata "Class Skills".
    lst = (
        "Class Skills\tKEY:Alchemist ~ Class Skills\tCATEGORY:Internal\t"
        "CSKILL:Appraise|TYPE=Craft|Disable Device\n"
    )
    voci = pcs.from_abilities_file(lst, "APG")

    assert len(voci) == 1
    assert voci[0]["class"] == "Alchemist", "la classe viene dalla KEY"
    assert voci[0]["skills"] == ["Appraise", "TYPE=Craft", "Disable Device"]


def test_anche_la_forma_breve_tilde_skills():
    """`KEY:<Classe> ~ Skills`, senza la parola 'Class'.

    E' la forma con cui PCGen dichiara l'Unchained Rogue -- la classe piu' usata
    fra quelle che restavano scoperte (16 schede sul dato utente). Cercare solo
    `~ Class Skills` la lasciava fuori.

    ⚠️ Il pattern e' piu' LARGO degli altri due: `~ Skills` puo' finire su
    un'abilita' che con le abilita' di classe non c'entra. Per questo la voce
    conta solo se porta anche un `CSKILL` -- il test qui sotto lo verifica al
    contrario.
    """
    from tools import import_pcgen_class_skills as pcs

    lst = (
        "Skills\tKEY:Unchained Rogue ~ Skills\tCATEGORY:Special Ability\t"
        "CSKILL:Acrobatics|Bluff|Stealth\n"
        # Stessa forma di chiave, NESSUN CSKILL: non e' una lista di abilita'
        # di classe e non deve entrare.
        "Skills\tKEY:Qualcosa ~ Skills\tCATEGORY:Special Ability\tTYPE:Altro\n"
    )
    voci = pcs.from_abilities_file(lst, "PU")

    assert [v["class"] for v in voci] == ["Unchained Rogue"]
    assert voci[0]["skills"] == ["Acrobatics", "Bluff", "Stealth"]
