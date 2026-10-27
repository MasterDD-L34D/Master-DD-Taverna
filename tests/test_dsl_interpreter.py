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


def test_update_build_merge_parciale(interp: Interpreter):
    before = copy.deepcopy(interp.state)
    interp.run_command("/update_build", nome="Grog", razza="Mezzorco")
    bs = interp.state["build_state"]
    # ADR 008 (ri-pin 2026-10-27): i campi dichiarati-non passati NON sono
    # piu' azzerati a None — le scritture su param non legato sono no-op e
    # i campi restano ASSENTI; statistiche_chiave azzerato e poi RICOSTRUITO
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
        assert campo not in bs, f"{campo} atteso assente, trovato {bs[campo]!r}"
    assert bs["nome"] == "Grog"
    assert bs["razza"] == "Mezzorco"
    assert bs["statistiche_chiave"] == {"CA": 10, "meta_tier": "Tier1"}
    assert bs["fonti_meta"] == []
    assert bs["derived"]["core"] == {"initiative_mod": 0, "speed_total": 30}
    # evento aggregato ADR 008: il merge parziale e' documentato, mai silenzioso
    ev = [e for e in interp.events if "update_parziale" in e]
    assert ev and ev[0]["update_parziale"]["comando"] == "/update_build"
    # nessuna mutazione fuori dai campi del comando, i suoi derivati e i
    # sotto-stati scritti dal /run_benchmark annidato (meta_cache, label)
    diff = {
        k
        for k in interp.state["build_state"]
        if interp.state["build_state"][k] != before["build_state"].get(k)
    }
    atteso = {
        "nome",
        "razza",
        "statistiche_chiave",
        "fonti_meta",
        "sinergie",
        "derived",
        "benchmarks",
        "meta_cache",
        "benchmark_reference_label",
    }
    assert diff <= atteso, f"mutazioni fuori perimetro: {diff - atteso}"


def test_set_profile_param_non_passato_assente(interp: Interpreter):
    interp.run_command("/set_profile", lingue="Elfico, Comune", allineamento="CN")
    profile = interp.state["build_state"]["profile"]
    assert profile["lingue"] == "Elfico, Comune"
    assert profile["allineamento"] == "CN"
    # ADR 008 (ri-pin 2026-10-27): xp dichiarato non passato = non legato:
    # la scrittura e' no-op, la chiave resta ASSENTE (non None)
    assert "xp" not in profile


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


# ---- ES2: update parziale (ADR 008 — merge su param non legato) ----

UPDATE_MINI = """
commands:
  /update:
    params: [nome, ruolo, classi]
    action:
      - set: build_state.nome
        value: "{{ nome }}"
      - set: build_state.ruolo
        value: "{{ ruolo }}"
      - set: build_state.classi
        value: "{{ classi }}"
"""


def test_update_parciale_merge_e_evento(tmp_path):
    # param non legato: no-op, lo stato conserva il valore esistente
    it = Interpreter(_mini(tmp_path, UPDATE_MINI))
    it.state["build_state"]["ruolo"] = "Tank"
    it.run_command("/update", nome="Grog")
    assert it.state["build_state"]["nome"] == "Grog"
    assert it.state["build_state"]["ruolo"] == "Tank"  # non azzerato
    ev = [e for e in it.events if "update_parziale" in e]
    assert ev, f"evento mancante: {it.events}"
    assert ev[0]["update_parziale"]["comando"] == "/update"
    assert ev[0]["update_parziale"]["saltati"] == [
        "build_state.ruolo",
        "build_state.classi",
    ]


def test_param_none_esplicito_e_cancellazione_voluta(tmp_path):
    # None PASSATO esplicitamente e' legato: scrive None, non e' un salto
    it = Interpreter(_mini(tmp_path, UPDATE_MINI))
    it.run_command("/update", nome="Grog", ruolo=None)
    assert "ruolo" in it.state["build_state"]  # scritto (None), non saltato
    ev = [e for e in it.events if "update_parziale" in e]
    assert "build_state.ruolo" not in ev[0]["update_parziale"]["saltati"]


def test_template_misto_salta_intera_action(tmp_path):
    # '{{nome}} {{ruolo}}' con ruolo non legato: niente scrittura parziale falsa
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [nome, ruolo]\n    action:\n"
        '      - set: build_state.etichetta\n        value: "{{ nome }} {{ ruolo }}"\n',
    )
    it = Interpreter(k)
    it.run_command("/go", nome="Grog")
    assert "etichetta" not in it.state["build_state"]
    assert any(
        "build_state.etichetta" in e.get("update_parziale", {}).get("saltati", [])
        for e in it.events
    )


def test_contaminazione_scratch_return_as(tmp_path):
    # call saltato con return_as -> tmp non legato per il resto del comando
    k = _mini(
        tmp_path,
        "helpers:\n  doppia:\n    params: [v]\n    logic: |\n      return (v or 0) * 2\n"
        "commands:\n  /go:\n    params: [x]\n    action:\n"
        "      - call: doppia\n        with: {v: '{{ x }}'}\n        return_as: tmp\n"
        "      - set: build_state.risultato\n        value: '{{ tmp }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "risultato" not in it.state["build_state"]
    saltati = [e for e in it.events if "update_parziale" in e][0]["update_parziale"][
        "saltati"
    ]
    assert "call:doppia" in saltati and "build_state.risultato" in saltati


def test_spec_comando_token_non_legato_scolto(tmp_path):
    # '/inner count={{ n }}' con n non legato: il token viene scartato e
    # /inner vede count non legato (no wipe silenzioso 'count=None')
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [count]\n"
        "    action: [{set: build_state.count, value: '{{ count }}'}]\n"
        "  /go:\n    params: [n]\n    action: [{command: '/inner count={{ n }}'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "count" not in it.state["build_state"]
    eventi = [e["update_parziale"] for e in it.events if "update_parziale" in e]
    assert any(
        ev["comando"] == "/inner" and ev["param_non_legati"] == ["count"]
        for ev in eventi
    )
    assert any(any(s.startswith("arg:") for s in ev["saltati"]) for ev in eventi)


def test_value_null_vietato_al_caricamento(tmp_path):
    # value: null su verbo mutante = gate rosso (ADR 008, divieto)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action: [{set: build_state.x, value: null}]\n",
    )
    esiti = k.static_check()
    assert esiti["null_errori"], "divieto value:null non rilevato"


def test_value_assente_su_set_vietato(tmp_path):
    # value mancante su set (a.get('value') -> None) = stesso wipe: vietato
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action: [{set: build_state.x}]\n",
    )
    assert k.static_check()["null_errori"], "value assente non rilevato"


# ---- ES2: review Codex PR #553 (4 findings P2) ----


def test_nome_da_chiave_stato_flatten_non_saltato(tmp_path):
    # Codex P2-1: '{{ name }}' che risolve a una chiave flatten di stato
    # (ctx.update(root) in _ctx) NON e' non legato: la scrittura avviene
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - set: build_state.name\n        value: Grog\n"
        "      - set: build_state.copia\n        value: '{{ name }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.state["build_state"]["copia"] == "Grog"
    assert not [e for e in it.events if "update_parziale" in e]


def test_guardia_is_not_none_mantiene_semantica_pre_es2(tmp_path):
    # Codex P2-2: le CONDIZIONI vedono il param dichiarato-non passato come
    # None (semantica pre-ES1, ADR 008: guardie mai scansionate). Senza il
    # fix, Undefined is not none -> True ed il ramo then scrive lo stesso
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [n]\n    action:\n"
        "      - if: '{{ n is not none }}'\n"
        "        then: [{set: build_state.x, value: pieno}]\n"
        "      - set: build_state.fuori\n        value: sempre\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "x" not in it.state["build_state"]  # ramo then NON entrato
    assert it.state["build_state"]["fuori"] == "sempre"
    it2 = Interpreter(k)
    it2.run_command("/go", n=5)
    assert it2.state["build_state"]["x"] == "pieno"


def test_posizionale_dropped_non_shifta_i_successivi(tmp_path):
    # Codex P2-3: '/inner {{ a }} {{ b }}' con solo b legato: il token di a
    # e' scartato ma il suo slot posizionale resta — b arriva a 'second'
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [first, second]\n"
        "    action:\n"
        "      - set: build_state.f\n        value: '{{ first }}'\n"
        "      - set: build_state.s\n        value: '{{ second }}'\n"
        "  /go:\n    params: [b]\n"
        "    action: [{command: '/inner {{ a }} {{ b }}'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go", b="B")
    assert it.state["build_state"]["s"] == "B"
    assert "f" not in it.state["build_state"]


def test_quoted_arg_con_template_dropped_intero(tmp_path):
    # Codex P2-4: 'text="{{ n }} suffix"' con n non legato: l'argomento
    # quoted e' UN token — drop intero, mai ValueError di shlex per quote
    # spezzate ne' scrittura parziale
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [text]\n"
        "    action: [{set: build_state.t, value: '{{ text }}'}]\n"
        "  /go:\n    params: [n]\n"
        "    action: [{command: '/inner text=\"{{ n }} suffix\"'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "t" not in it.state["build_state"]
    saltati = [
        s for e in it.events for s in e.get("update_parziale", {}).get("saltati", [])
    ]
    assert any(s.startswith("arg:") for s in saltati)
    # con n legato il quoted arg rende intero e viene scritto
    it2 = Interpreter(k)
    it2.run_command("/go", n="N")
    assert it2.state["build_state"]["t"] == "N suffix"


# ---- ES2: review Codex PR #553 giro 2 (3 findings P2) ----


def test_filtro_o_aritmetica_su_non_legato_dropped_prima_del_render(tmp_path):
    # Codex P2 (giro 2): '/inner count={{ n|int }}' con n omesso — la
    # sentinella-stringa verrebbe coercita dal filtro (count=0, wipe muto)
    # e '{{ n + 1 }}' abortirebbe col TypeError. Il token va droppato PRIMA
    # del render: nessuna scrittura, nessun abort, arg: registrato
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [count]\n"
        "    action: [{set: build_state.c, value: '{{ count }}'}]\n"
        "  /go:\n    params: [n]\n"
        "    action:\n"
        "      - command: '/inner count={{ n|int }}'\n"
        "      - command: '/inner count={{ n + 1 }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")  # non deve alzare TypeError
    assert "c" not in it.state["build_state"]
    saltati = [
        s for e in it.events for s in e.get("update_parziale", {}).get("saltati", [])
    ]
    assert len([s for s in saltati if s.startswith("arg:")]) == 2


def test_fallback_per_occorrenza_non_per_nome(tmp_path):
    # Codex P2 (giro 2): '{{ n|default("fallback") }} {{ n }}' con n omesso
    # — l'occorrenza NON protetta rende il template misto: salta tutto
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [n]\n"
        "    action:\n"
        "      - set: build_state.x\n"
        "        value: '{{ n|default(\"fallback\") }} {{ n }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "x" not in it.state["build_state"]
    it2 = Interpreter(k)
    it2.run_command("/go", n="N")
    assert it2.state["build_state"]["x"] == "N N"  # n legato: default non scatta


def test_call_saltato_invalida_scratch_stale(tmp_path):
    # Codex P2 (giro 2): call con return_as saltata dopo che tmp e' stato
    # valorizzato — il valore stale non deve sopravvivere: il set dipendente
    # salta (tmp e' di nuovo non risolvibile)
    k = _mini(
        tmp_path,
        "helpers:\n  doppia:\n    params: [v]\n    logic: |\n      return (v or 0) * 2\n"
        "commands:\n  /go:\n    params: [n]\n    action:\n"
        "      - call: doppia\n        with: {v: 1}\n        return_as: tmp\n"
        "      - call: doppia\n        with: {v: '{{ n }}'}\n        return_as: tmp\n"
        "      - set: build_state.risultato\n        value: '{{ tmp }}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert "risultato" not in it.state["build_state"]
    saltati = [
        s for e in it.events for s in e.get("update_parziale", {}).get("saltati", [])
    ]
    assert "call:doppia" in saltati and "build_state.risultato" in saltati
