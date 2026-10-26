"""Gate ES1 (piano planning/2026-10-26-esecutore-dsl-fase0.md).

Replay deterministico di comandi reali di minmax_builder + copertura G2
+ gate statico G3. Zero LLM, zero random/now nei comandi di replay.
"""

import copy
import json
from pathlib import Path

import pytest

from src.dsl.loader import Kernel, load_kernel
from src.dsl.interpreter import Interpreter

MODULES = Path(__file__).resolve().parent.parent / "src" / "modules"


@pytest.fixture(scope="module")
def kernel() -> Kernel:
    return load_kernel(MODULES)  # tutti i moduli: per G2 copertura e G3


@pytest.fixture(scope="module")
def kernel_minmax() -> Kernel:
    # replay G1: solo kernel + minmax — nomi comando omonimi tra moduli
    # (es. /update_build in Taverna_NPC) risolti dal perimetro del replay
    return load_kernel(MODULES, only=("minmax_builder.txt",))


@pytest.fixture()
def interp(kernel_minmax: Kernel):
    return Interpreter(kernel_minmax)


# ---- G1 replay: semantica reale dei file (oracoli seguono il modulo) ----


def test_toggle_rules_pfs_on(interp: Interpreter):
    interp.run_command("/toggle_rules", pfs="on")
    assert interp.state["build_state"]["rules"]["pfs_active"] is True
    # binding D8: abp/eitr NON passati -> condizione falsa, nessuna scrittura
    assert not interp.state["build_state"]["rules"].get("abp_active")


def test_toggle_rules_abp_off(interp: Interpreter):
    interp.state["build_state"].setdefault("rules", {})["abp_active"] = True
    interp.run_command("/toggle_rules", abp="off")
    assert interp.state["build_state"]["rules"]["abp_active"] is False


def test_update_build_sovrascrive_tutti_i_campi(interp: Interpreter):
    before = copy.deepcopy(interp.state)
    interp.run_command("/update_build", nome="Grog", razza="Mezzorco")
    bs = interp.state["build_state"]
    # semantica reale del file (pin 2026-10-26): 8 campi dichiarati-non
    # passati riscritti a None; statistiche_chiave azzerato e poi RICOSTRUITO
    # dai derived del comando stesso; fonti_meta svuotato dalla scan branch
    for campo in ("ruolo", "classi", "statistiche", "salvezze", "tratti",
                  "background", "fonti"):
        assert bs[campo] is None, f"{campo} atteso None, trovato {bs[campo]!r}"
    assert bs["nome"] == "Grog"
    assert bs["razza"] == "Mezzorco"
    assert bs["statistiche_chiave"] == {"CA": 10, "meta_tier": "Tier1"}
    assert bs["fonti_meta"] == []
    assert bs["derived"]["core"] == {"initiative_mod": 0, "speed_total": 30}
    # nessuna mutazione fuori dai campi del comando, i suoi derivati e i
    # sotto-stati scritti dal /run_benchmark annidato (meta_cache, label)
    diff = {
        k
        for k in interp.state["build_state"]
        if interp.state["build_state"][k] != before["build_state"].get(k)
    }
    atteso = {"nome", "ruolo", "classi", "razza", "statistiche", "salvezze",
              "tratti", "statistiche_chiave", "background", "fonti",
              "fonti_meta", "sinergie", "derived", "benchmarks",
              "meta_cache", "benchmark_reference_label"}
    assert diff <= atteso, f"mutazioni fuori perimetro: {diff - atteso}"


def test_set_profile_scrittura_annidata(interp: Interpreter):
    interp.run_command("/set_profile", lingue="Elfico, Comune", allineamento="CN")
    assert interp.state["build_state"]["profile"]["lingue"] == "Elfico, Comune"
    assert interp.state["build_state"]["profile"]["allineamento"] == "CN"
    # param dichiarato non passato: riscritto a None (semantica D2)
    assert interp.state["build_state"]["profile"]["xp"] is None


# ---- G2 copertura: ogni comando dei moduli classificato ----


def test_copertura_comandi(kernel: Kernel, tmp_path):
    report = Interpreter(kernel).coverage_report()
    (tmp_path / "dsl_coverage.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    assert report["totale"] >= 240, f"comandi attesi >= 240, {report['totale']}"
    assert not report["errore"], (
        f"verbi sconosciuti: {report['errore'][:10]}"
    )
    # i verbi no-op devono essere dichiarati (lista nominale), non silenziosi
    assert isinstance(report["no_op_cmds"], list)


# ---- G3 statico: compile logic + parse template ----
# Lista nominale pinna i 23 referti attesi (misura 2026-10-26): sono fuori
# dai percorsi eseguiti da ES1 — documentazione brew (meta_doc), mini-lingua
# @var@ dello state_machine e condizioni con comprehension python dei moduli
# (latenti, mai eseguite dal modello; fix modulo = fuori scope D2).
G3_PIN = {
    'Taverna_NPC.txt: commands./quiz_bestworst <set_id> best="<opzione>" worst="<opzione>".action[3].with.bank',
    'Taverna_NPC.txt: commands./quiz_start.action[6].with.bank',
    'Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.items.actions[1].params.gp',
    'Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits.guards[0].condition',
    'Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits.when',
    'Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits_random.actions[0].with.total',
    'Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits_random.when',
    'Taverna_NPC.txt: state_machine.GameMode.Gambling.play.actions[2].then[0].params.gp',
    'Taverna_NPC.txt: state_machine.GameMode.Gambling.play.actions[2].then[1].value',
    'Taverna_NPC.txt: state_machine.GameMode.KingdomTurn.when',
    'Taverna_NPC.txt: state_machine.GameMode.MassCombat.when',
    'Taverna_NPC.txt: state_machine.GameMode.OnboardingTheme.gender_age.actions[2].output',
    'Taverna_NPC.txt: state_machine.GameMode.OnboardingTheme.portrait.actions[0].then[1].output',
    'Taverna_NPC.txt: state_machine.GameMode.SoloLoop.actions[0].with.ctt_map',
    'Taverna_NPC.txt: state_machine.GameMode.SoloLoop.actions[0].with.traits',
    'meta_doc.txt: commands./brew_lint.action[0].output',
    'meta_doc.txt: commands./render_brew_example.action[0].cases[13].do[0].output',
    'meta_doc.txt: commands./render_brew_example.action[0].cases[14].do[0].output',
    'meta_doc.txt: commands./render_brew_example.action[0].cases[15].do[0].output',
    'meta_doc.txt: commands./render_brew_example.action[0].cases[17].do[0].output',
    'minmax_builder.txt: commands./add_meta_source.action[0].if',
    'minmax_builder.txt: commands./risk_heatmap.action[4].output',
    'minmax_builder.txt: commands./run_benchmark.action[3].then[2].actions[2].if',
}


def test_g3_statico(kernel: Kernel):
    esiti = kernel.static_check()
    assert esiti["logic_errori"] == [], esiti["logic_errori"][:5]
    prefissi = {t.split(": TemplateSyntaxError")[0]
                for t in esiti["template_errori"]}
    assert prefissi == G3_PIN, (
        f"nuovi referti non pinna: {sorted(prefissi - G3_PIN)[:5]}; "
        f"scomparsi: {sorted(G3_PIN - prefissi)[:5]}")
