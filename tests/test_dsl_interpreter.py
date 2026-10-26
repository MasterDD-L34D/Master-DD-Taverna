"""Gate ES1 (piano planning/2026-10-26-esecutore-dsl-fase0.md).

Replay deterministico di comandi reali di minmax_builder + copertura G2
+ gate statico G3. Zero LLM, zero random/now nei comandi di replay.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from src.dsl.loader import Kernel, load_kernel
from src.dsl.interpreter import DslAbort, Interpreter

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
    for campo in (
        "ruolo",
        "classi",
        "statistiche",
        "salvezze",
        "tratti",
        "background",
        "fonti",
    ):
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
    atteso = {
        "nome",
        "ruolo",
        "classi",
        "razza",
        "statistiche",
        "salvezze",
        "tratti",
        "statistiche_chiave",
        "background",
        "fonti",
        "fonti_meta",
        "sinergie",
        "derived",
        "benchmarks",
        "meta_cache",
        "benchmark_reference_label",
    }
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
    assert not report["errore"], f"verbi sconosciuti: {report['errore'][:10]}"
    # i verbi no-op devono essere dichiarati (lista nominale), non silenziosi
    assert isinstance(report["no_op_cmds"], list)


# ---- G3 statico: compile logic + parse template ----
# Lista nominale pinna i 18 referti attesi (misura 2026-10-27, cantiere 0):
# documentazione brew di meta_doc (5) e mini-lingua @var@ dello state_machine
# di Taverna_NPC (13) — fuori perimetro fino a decisione ES2. Le comprehension
# Python (4) e il dict vuoto di /risk_heatmap sono stati curati in cantiere 0.
G3_PIN = {
    "Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.items.actions[1].params.gp",
    "Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits.guards[0].condition",
    "Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits.when",
    "Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits_random.actions[0].with.total",
    "Taverna_NPC.txt: state_machine.GameMode.BackgroundTraits.traits_random.when",
    "Taverna_NPC.txt: state_machine.GameMode.Gambling.play.actions[2].then[0].params.gp",
    "Taverna_NPC.txt: state_machine.GameMode.Gambling.play.actions[2].then[1].value",
    "Taverna_NPC.txt: state_machine.GameMode.KingdomTurn.when",
    "Taverna_NPC.txt: state_machine.GameMode.MassCombat.when",
    "Taverna_NPC.txt: state_machine.GameMode.OnboardingTheme.gender_age.actions[2].output",
    "Taverna_NPC.txt: state_machine.GameMode.OnboardingTheme.portrait.actions[0].then[1].output",
    "Taverna_NPC.txt: state_machine.GameMode.SoloLoop.actions[0].with.ctt_map",
    "Taverna_NPC.txt: state_machine.GameMode.SoloLoop.actions[0].with.traits",
    "meta_doc.txt: commands./brew_lint.action[0].output",
    "meta_doc.txt: commands./render_brew_example.action[0].cases[13].do[0].output",
    "meta_doc.txt: commands./render_brew_example.action[0].cases[14].do[0].output",
    "meta_doc.txt: commands./render_brew_example.action[0].cases[15].do[0].output",
    "meta_doc.txt: commands./render_brew_example.action[0].cases[17].do[0].output",
}


def test_g3_statico(kernel: Kernel):
    esiti = kernel.static_check()
    assert esiti["logic_errori"] == [], esiti["logic_errori"][:5]
    # BASSA-13: pin normalizzato — gli indici degli array non contano
    # (fix modulo che sposta una action non deve far saltare il gate);
    # vige il vincolo "nessun referto nuovo e conteggio non cresce"
    # (evita il treadmill da indici senza perdere la segnalazione).
    norm = lambda s: re.sub(r"\[\d+\]", "[]", s)
    pin = {norm(t) for t in G3_PIN}
    prefissi = {
        norm(t.split(": TemplateSyntaxError")[0]) for t in esiti["template_errori"]
    }
    assert prefissi <= pin, f"nuovi referti non pinna: {sorted(prefissi - pin)[:5]}"
    assert len(esiti["template_errori"]) <= len(
        G3_PIN
    ), f"referti cresciuti: {len(esiti['template_errori'])} > {len(G3_PIN)}"


# ---- difese (rilevi ALTA/MEDIA della review Claude su PR #550) ----
# Kernel sintetici in tmp_path: load_kernel prende una directory, quindi
# un mini modulo YAML basta per isolare ogni difesa.


def _mini(tmp_path: Path, yaml_text: str) -> Kernel:
    (tmp_path / "mini.txt").write_text(yaml_text, encoding="utf-8")
    return load_kernel(tmp_path)


RECURSIVI = """
commands:
  /a:
    action: [{command: /b}]
  /b:
    action: [{command: /a}]
"""


def test_ricorsione_command_abortisce(tmp_path):
    # ALTA-2: /a <-> /b devono abortire con DslAbort, non con RecursionError
    with pytest.raises(DslAbort):
        Interpreter(_mini(tmp_path, RECURSIVI)).run_command("/a")


def test_helper_import_non_permesso(tmp_path):
    # ALTA-1: la whitelist import deve mordere davvero (import os -> ImportError)
    k = _mini(
        tmp_path,
        "helpers:\n  bad:\n    logic: |\n      import os\n      return 1\n"
        "commands:\n  /go:\n    action: [{call: bad}]\n",
    )
    with pytest.raises(ImportError):
        Interpreter(k).run_command("/go")


def test_helper_eval_negato(tmp_path):
    # ALTA-1: senza builtins veri nel globals, eval non esiste -> NameError
    k = _mini(
        tmp_path,
        "helpers:\n  bad:\n    logic: |\n      return eval('1+1')\n"
        "commands:\n  /go:\n    action: [{call: bad}]\n",
    )
    with pytest.raises(NameError):
        Interpreter(k).run_command("/go")


def test_foreach_su_nome_scratch_e_stato(tmp_path):
    # ALTA-3: foreach su nome senza punto risolve nello stato (non i caratteri)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - set: items\n        value: [1, 2]\n"
        "      - foreach: items\n        actions:\n"
        "          - output: '{{ item }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == ["1", "2"]


def test_foreach_nome_mancante_evento_e_stato_intatto(tmp_path):
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - foreach: nome_mancante\n        actions:\n"
        "          - set: build_state.colpito\n            value: 1\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.events and "foreach_non_risolto" in it.events[0]
    assert "colpito" not in it.state["build_state"]


def test_parse_json_in_scratch_e_foreach(tmp_path):
    # ALTA-3: lo scratch e' consultato dal foreach (parse_json -> as -> loop)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        '      - parse_json: {input: \'[{"v": 1}, {"v": 2}]\', as: rows}\n'
        "      - foreach: rows\n        actions:\n"
        "          - output: '{{ item.v }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == ["1", "2"]


def test_action_dict_singolo_normalizzato(tmp_path):
    # MEDIA-4: then: {command: /x} (dict invece di lista) non e' piu' silenzioso
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - if: '{{ 1 }}'\n        then: {command: /inner}\n"
        "  /inner:\n    action: [{set: build_state.x, value: ok}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.state["build_state"]["x"] == "ok"


def test_argomenti_posizionali_legati_e_extra_segnalati(tmp_path):
    # MEDIA-5: /bench -q lega -q al primo param dichiarato; l'extra e' evento
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [q]\n"
        "    action: [{set: build_state.q, value: '{{ q }}'}]\n"
        "  /bare:\n    action: [{output: x}]\n"
        "  /go:\n    action:\n      - command: /inner -q\n"
        "      - command: /bare extra\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.state["build_state"]["q"] == "-q"
    assert any("argomento_posizionale_scolto" in e for e in it.events)


def test_precedenza_stato_su_dati_modulo(tmp_path):
    # MEDIA-6: una chiave di stato vince sul dato top-level omonimo del modulo
    k = _mini(
        tmp_path,
        "saluto: dal_modulo\ncommands:\n  /go:\n    action:\n"
        "      - set: build_state.saluto\n        value: dallo_stato\n"
        "      - output: '{{ saluto }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == ["dallo_stato"]


def test_scratch_non_tracima_al_chiamante(tmp_path):
    # MEDIA-8: lo scratch scritto da un comando annidato muore con lui
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    action:\n"
        "      - parse_json: {input: '[1]', as: leaked}\n"
        "  /go:\n    action:\n      - command: /inner\n"
        "      - foreach: leaked\n        actions:\n"
        "          - output: '{{ item }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == []
    assert any("foreach_non_risolto" in e for e in it.events)


def test_templates_in_scende_nei_cases(tmp_path):
    # BASSA-10: il gate G2 vede i template citati dentro cases[].do
    k = _mini(
        tmp_path,
        "ui_templates:\n  ok: fine\n"
        "commands:\n  /go:\n    action:\n"
        "      - switch: '{{ 1 }}'\n        cases:\n"
        "          - when: '1'\n            do:\n"
        "              - output_template: ok\n"
        "          - when: '2'\n            do:\n"
        "              - output_template: mancante\n",
    )
    report = Interpreter(k).coverage_report()
    assert report["errore"], "template mancante dentro cases non segnalato"
    assert report["errore"][0]["template_mancanti"] == ["mancante"]


def test_lookup_primo_token_nomi_con_firma(tmp_path):
    # BASSA-13: il dizionario chiave per nome intero, il modello scrive il
    # primo token; il placeholder <set_id> lega il posizionale
    k = _mini(
        tmp_path,
        "commands:\n"
        '  /quiz_bestworst <set_id> best="<opzione>" worst="<opzione>":\n'
        "    action: [{set: build_state.scelta, value: '{{ set_id }}'}]\n"
        "  /go:\n    action: [{command: '/quiz_bestworst s01 best=a worst=b'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.state["build_state"]["scelta"] == "s01"


def test_set_ricorsivo_su_mapping_e_liste(tmp_path):
    # Codex P1: value mapping/lista con template annidati -> resi, non literal
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [nome]\n    action:\n"
        "      - set: build_state.anagrafica\n        value:\n"
        "          nome: '{{ nome }}'\n          tags: ['{{ nome }}']\n",
    )
    it = Interpreter(k)
    it.run_command("/go", nome="Ada")
    assert it.state["build_state"]["anagrafica"] == {"nome": "Ada", "tags": ["Ada"]}


def test_command_con_template_reso_prima_di_tokenizzare(tmp_path):
    # Codex P2: /inner count={{ n or 3 }} lega count=3, non count="{{"
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [count]\n"
        "    action: [{set: build_state.count, value: '{{ count }}'}]\n"
        "  /go:\n    action: [{command: '/inner count={{ n or 3 }}'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.state["build_state"]["count"] == 3  # int nativo, non stringa


def test_helper_sotto_namespace(tmp_path):
    # Codex P3: helpers Echo.saluta (namespace) caricati e chiamabili via call
    k = _mini(
        tmp_path,
        "helpers:\n  Echo:\n    saluta:\n      params: [nome]\n"
        "      logic: |\n        return 'ciao ' + nome\n"
        "commands:\n  /go:\n    action:\n"
        "      - call: Echo.saluta\n        with: {nome: Ada}\n"
        "        return_as: res\n      - output: '{{ res }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == ["ciao Ada"]


def test_compute_forma_espresione(tmp_path):
    # Codex P4: logic template su riga unica = espressione, non corpo Python
    k = _mini(
        tmp_path,
        "helpers:\n  doppia:\n    params: [x]\n    logic: |\n      return x * 2\n"
        "commands:\n  /go:\n    params: [n, q, v]\n    action:\n"
        "      - compute: uno\n        logic: '{{ doppia(n) }}'\n"
        "      - compute: due\n        logic: '{{q|int}} * {{v|float}}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go", n=4, q=3, v=2.5)
    assert it.state["uno"] == 8
    assert it.state["due"] == 7.5
