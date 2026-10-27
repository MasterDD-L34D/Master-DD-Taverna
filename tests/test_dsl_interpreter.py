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
from src.dsl.state import get_path

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
    # ADR 008 (Codex P2 giro 4): il divieto value:null e' un gate vero,
    # non solo un campo restituito — sui moduli del repo deve essere vuoto
    assert esiti["null_errori"] == [], esiti["null_errori"][:5]
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


# ---- ES2: review Codex PR #553 giro 3 (2 findings P2) ----


def test_variabili_locali_jinja_non_sono_non_legate(tmp_path):
    # Codex P2 (giro 3): le variabili bound dai loop/set interni al
    # template ('{% for x in values %}{{ x }}') NON sono dipendenze esterne:
    # la scansione deve essere scope-aware come find_undeclared_variables
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [values]\n"
        "    action:\n"
        "      - set: build_state.xs\n"
        "        value: '{% for x in values %}{{ x }}{% endfor %}'\n",
    )
    it = Interpreter(k)
    it.run_command("/go", values=[1, 2])
    assert it.state["build_state"]["xs"] == 12  # native env: output adiacenti
    assert not [e for e in it.events if "update_parziale" in e]


def test_uguale_in_template_non_rende_named_l_argomento(tmp_path):
    # Codex P2 (giro 3): '{{ n == 1 }}' e' un argomento POSIZIONALE (l'= e'
    # dentro l'espressione): renderizzato a 'True' deve legarsi al param
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [flag]\n"
        "    action: [{set: build_state.f, value: '{{ flag }}'}]\n"
        "  /go:\n    params: [n]\n"
        "    action: [{command: '/inner {{ n == 1 }}'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go", n=1)
    assert it.state["build_state"]["f"] is True  # bool nativo dal render


# ---- ES2: review Codex PR #553 giro 4 (2 findings P2 + gate collegato) ----


def test_fallback_protetto_maschera_param_omesso_su_omonimo_stato(tmp_path):
    # Codex P2 (giro 4): '{{ n or 3 }}' con n dichiarato omesso deve
    # risolvere il fallback (3, semantica pre-ES1), non l'omonima chiave di
    # stato (build_state.n = 7)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [n]\n"
        "    action:\n"
        "      - set: build_state.altro\n        value: '{{ n or 3 }}'\n",
    )
    it = Interpreter(k)
    it.state["build_state"]["n"] = 7
    it.run_command("/go")
    assert it.state["build_state"]["altro"] == 3


def test_template_che_espande_in_piu_argomenti_mantiene_slot(tmp_path):
    # Codex P2 (giro 4): '{{ words }}' non quotato con words='one two' rende
    # DUE argomenti shlex — i successivi argomenti prendono gli slot in
    # sequenza ('tail' non va scartato)
    k = _mini(
        tmp_path,
        "commands:\n  /inner:\n    params: [first, second, third]\n"
        "    action:\n"
        "      - set: build_state.f\n        value: '{{ first }}'\n"
        "      - set: build_state.s\n        value: '{{ second }}'\n"
        "      - set: build_state.t\n        value: '{{ third }}'\n"
        "  /go:\n    params: [words]\n"
        "    action: [{command: '/inner {{ words }} tail'}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go", words="one two")
    assert it.state["build_state"]["f"] == "one"
    assert it.state["build_state"]["s"] == "two"
    assert it.state["build_state"]["t"] == "tail"


# ---- ES2-a1: archivio sessione (ADR 009) ----


class FakePort:
    """Porta in-memory (ADR 009): i verbi non toccano disco/bus diretti."""

    def __init__(self):
        self.data: dict = {}
        self.events_log: list = []

    def save(self, key, value):
        self.data[key] = value

    def load(self, key):
        return self.data.get(key)

    def list(self, prefix):
        return sorted(k for k in self.data if k.startswith(prefix))

    def emit(self, topic, payload):
        self.events_log.append({"topic": topic, "payload": payload})


SESSIONE_MINI = """
commands:
  /save:
    params: [nome]
    action:
      - set: build_state.nome
        value: '{{ nome }}'
      - save_session:
          key: 'build_{{ nome }}'
          value: '{{ build_state }}'
  /load:
    params: [nome]
    action:
      - load_session:
          key: 'build_{{ nome }}'
          as: loaded
      - if: '{{ loaded is not none }}'
        then:
          - set: build_state.riportato
            value: '{{ loaded.nome }}'
  /list:
    action:
      - list_session_keys:
          prefix: build_
          as: keys
      - set: build_state.n_keys
        value: '{{ keys | length }}'
"""


def test_save_e_load_session_via_porta(tmp_path):
    # ADR 009: save scrive il nodo reso sulla porta, load lo riporta e la
    # guardia 'is not None' dei moduli funziona
    k = _mini(tmp_path, SESSIONE_MINI)
    port = FakePort()
    it = Interpreter(k, port=port)
    it.state["build_state"]["punteggi"] = {"for": 16}
    it.run_command("/save", nome="Grog")
    assert port.data["build_Grog"]["punteggi"] == {"for": 16}
    it.run_command("/load", nome="Grog")
    assert it.state["build_state"]["riportato"] == "Grog"


def test_load_assente_da_none_e_nessun_evento_difetto(tmp_path):
    k = _mini(tmp_path, SESSIONE_MINI)
    port = FakePort()
    it = Interpreter(k, port=port)
    it.run_command("/load", nome="Mancante")
    assert "riportato" not in it.state["build_state"]
    assert not [e for e in it.events if "load" in str(e)]


def test_list_session_keys_filtra_per_prefisso(tmp_path):
    k = _mini(tmp_path, SESSIONE_MINI)
    port = FakePort()
    port.data = {"build_A": {}, "build_B": {}, "enc_C": {}}
    it = Interpreter(k, port=port)
    it.run_command("/list")
    assert it.state["build_state"]["n_keys"] == 2


def test_chiave_sessione_non_valida_rifiutata(tmp_path):
    # ADR 009 (confine fiducia): la chiave resa e' whitelist; il rifiuto e'
    # un evento, mai una sanificazione silenziosa
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [nome]\n    action:\n"
        "      - save_session:\n"
        "          key: 'build_{{ nome }}'\n          value: x\n",
    )
    port = FakePort()
    it = Interpreter(k, port=port)
    it.run_command("/go", nome="../escape")
    assert not port.data
    assert any("chiave" in str(e) for e in it.events)


def test_emit_event_su_porta(tmp_path):
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [termine]\n    action:\n"
        "      - emit_event:\n"
        "          topic: explain.theme\n"
        "          payload: {termine: '{{ termine }}', from: Test}\n",
    )
    port = FakePort()
    Interpreter(k, port=port).run_command("/go", termine="Attacco")
    assert port.events_log == [
        {"topic": "explain.theme", "payload": {"termine": "Attacco", "from": "Test"}}
    ]


def test_replace_placeholder_nella_variabile_di_loop(tmp_path):
    # forma reale di minmax_builder /run_benchmark: il pattern contiene il
    # placeholder letterale <classe>, risolto prima della search
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - set: local.classe\n        value: chierico\n"
        "      - foreach: meta_reference.patterns\n        loop_as: pattern\n"
        "        actions:\n"
        "          - replace_placeholder: <classe>\n"
        "            with: '{{ local.classe }}'\n"
        "          - output: '{{ pattern }}'\n",
    )
    k.data["meta_reference"] = {"patterns": ["DPR <classe> build", "<classe> tier"]}
    it = Interpreter(k)
    it.run_command("/go")
    assert it.output_log == ["DPR chierico build", "chierico tier"]


def test_goto_state_senza_state_machine_evento_e_nessuna_scrittura(tmp_path):
    # ADR 012: senza state_machine dichiarato il flat non e' validabile —
    # evento, mai silenzioso, nessuna scrittura (v4 del test ADR 009:
    # goto_state e' ora eseguibile, il rifiuto resta rendicontato)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action: [{goto_state: READY}]\n",
    )
    it = Interpreter(k)
    it.run_command("/go")
    assert it.noop_log == []
    assert [e.get("stato_non_valido") for e in it.events] == ["READY"]
    assert "runtime" not in it.state or "current_state" not in it.state.get(
        "runtime", {}
    )


def test_porta_json_persiste_su_disco(tmp_path):
    # ADR 009: JsonFilePort reale — round-trip tra due istanze, scrittura
    # atomica (tmp + os.replace), override del percorso via env
    from src.dsl.store import JsonFilePort

    path = tmp_path / "var" / "sessions" / "store.json"
    p1 = JsonFilePort(path)
    p1.save("build_Grog", {"punteggi": {"for": 16}})
    assert path.exists()
    p2 = JsonFilePort(path)
    assert p2.load("build_Grog") == {"punteggi": {"for": 16}}
    assert p2.list("build_") == ["build_Grog"]
    assert p2.load("mancante") is None


def test_save_e_snapshot_indipendente_dallo_stato_vivo(tmp_path):
    # P1 review Codex #554: la entry salvata non deve mutare quando il
    # build_state vivo viene modificato dopo il save
    k = _mini(tmp_path, SESSIONE_MINI)
    port = FakePort()
    it = Interpreter(k, port=port)
    it.state["build_state"]["punteggi"] = {"for": 16}
    it.run_command("/save", nome="Grog")
    it.state["build_state"]["punteggi"]["for"] = 99
    assert port.data["build_Grog"]["punteggi"]["for"] == 16


def test_porta_onora_env_path(tmp_path, monkeypatch):
    # P2 review Codex #554: MASTERS_DD_SESSIONS_PATH e' l'override di
    # deployment promesso dall'ADR 009, non decorazione
    from src.dsl.store import JsonFilePort

    target = tmp_path / "altro" / "store.json"
    monkeypatch.setenv("MASTERS_DD_SESSIONS_PATH", str(target))
    port = JsonFilePort()
    port.save("build_X", {"a": 1})
    assert target.exists()
    assert JsonFilePort().load("build_X") == {"a": 1}


def test_save_con_param_omesso_non_fabbrica_chiave(tmp_path):
    # P2 review Codex #554 giro 2: il param omesso non deve rendere la
    # chiave valida 'build_None' — la scrittura e' saltata con evento
    k = _mini(tmp_path, SESSIONE_MINI)
    port = FakePort()
    it = Interpreter(k, port=port)
    it.run_command("/save")  # nome omesso
    assert not port.data
    assert any("update_parziale" in str(e) for e in it.events)


def test_due_porte_stesso_file_non_si_sovrascrivono(tmp_path):
    # P1 review Codex #554 giro 2: read-modify-write — il save di B non
    # cancella l'entry scritta da A sulla stessa path
    from src.dsl.store import JsonFilePort

    path = tmp_path / "store.json"
    JsonFilePort(path).save("build_A", {"x": 1})
    JsonFilePort(path).save("build_B", {"x": 2})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"build_A": {"x": 1}, "build_B": {"x": 2}}


def test_load_e_list_vedono_save_di_altra_istanza(tmp_path):
    # P2 review Codex #554 giro 5: load/list rinfrescano dal disco — una
    # porta inizializzata PRIMA del save altrui non resta cieca all'entry
    from src.dsl.store import JsonFilePort

    path = tmp_path / "store.json"
    prima = JsonFilePort(path)
    JsonFilePort(path).save("build_Esterno", {"x": 1})
    assert prima.load("build_Esterno") == {"x": 1}
    assert prima.list("build_") == ["build_Esterno"]


def test_save_di_radice_stato_creata_dinamicamente(tmp_path):
    # P2 review Codex #554 giro 6: forked_build (/fork_build) e forked
    # (/fork_encounter) sono radici create dal comando stesso — _ctx le
    # espone a render, lo skip statico non deve trattarle come non legate
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [variant_id]\n    action:\n"
        "      - set: forked_build.variant_id\n        value: '{{ variant_id }}'\n"
        "      - save_session:\n"
        "          key: 'build_{{ variant_id }}'\n"
        "          value: '{{ forked_build }}'\n",
    )
    port = FakePort()
    Interpreter(k, port=port).run_command("/go", variant_id="variant1")
    assert port.data == {"build_variant1": {"variant_id": "variant1"}}


def test_valore_non_serializzabile_fallisce_esplicito(tmp_path):
    # ADR 009: mai str() silenzioso — evento e nessuna scrittura
    from src.dsl.store import JsonFilePort

    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - call: bad\n        return_as: raw\n"
        "      - save_session:\n"
        "          key: build_x\n"
        "          value: '{{ raw }}'\n",
    )
    # helper che rende un oggetto non JSON-serializzabile
    k.helpers["bad"] = {"params": [], "logic": "return object()", "origin": "t"}
    port = JsonFilePort(tmp_path / "store.json")
    it = Interpreter(k, port=port)
    it.run_command("/go")
    assert not (tmp_path / "store.json").exists()
    assert any("serializ" in str(e) for e in it.events)


def test_moduli_template_senza_is_not_None_maiuscolo():
    # P2 review Codex #554 giro 3: 'is not None' non e' un test jinja valido
    # ("No test named 'None'") — la guardia e' morta sempre falsa. I helper
    # python (logic) possono usare 'is not None' legitimo: si scansionano
    # solo le righe con template {{ ... }}
    for f in sorted(MODULES.glob("*.txt")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "{{" in line and "is not None" in line:
                pytest.fail(f"{f.name}:{i}: 'is not None' in template jinja")


# ---- ES2-a3: verbo export (ADR 010) ----


class FakeExportPort:
    """Porta export in-memory (ADR 010): i verbi non toccano disco.
    Replica la semantica di naming della porta vera: contatore dalla
    directory (qui: dal numero di file scritti)."""

    def __init__(self):
        self.files: dict = {}

    def write(self, ext: str, content: str) -> str:
        name = f"export_{len(self.files) + 1}.{ext}"
        self.files[name] = content
        return name


def test_export_persiste_ultimo_output(tmp_path):
    # forma reale (adventurer_ledger /export_pg_sheet_json): output_template
    # inline + export: json — il file contiene il render del template;
    # exported_path e' leggibile dagli action successivi dello stesso
    # comando (lo scratch non tracima fuori dal comando, MEDIA-8)
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action:\n"
        "      - output_template: |\n"
        '          {"wbl": {{ loot_state.wbl | tojson }}}\n'
        "      - export: json\n"
        "      - output: 'file: {{ exported_path }}'\n",
    )
    port = FakeExportPort()
    it = Interpreter(k, export_port=port)
    # lo stato popolato vince sui dati del kernel nel ctx (MEDIA-6):
    # la forma reale ha loot_state valorizzato dai comandi precedenti
    it.state["loot_state"]["wbl"] = {"current_gp": 100}
    it.run_command("/go")
    assert port.files == {"export_1.json": '{"wbl": {"current_gp": 100}}'}
    assert it.output_log[-1] == "file: export_1.json"


def test_export_formato_con_fallback_quando_param_assente(tmp_path):
    # forma reale (adventurer_ledger /export_loot): il fallback protetto
    # rende il formato, non e' un nome non legato
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [format]\n    action:\n"
        "      - output: loot doc\n"
        "      - export: '{{ format or \"markdown\" }}'\n",
    )
    port = FakeExportPort()
    Interpreter(k, export_port=port).run_command("/go")
    assert list(port.files) == ["export_1.markdown"]


def test_export_formato_non_in_whitelist_rifiutato(tmp_path):
    # confine fiducia (ADR 010): mai un nome file arbitrario da input utente
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    params: [format]\n    action:\n"
        "      - output: doc\n"
        "      - export: '{{ format }}'\n",
    )
    port = FakeExportPort()
    it = Interpreter(k, export_port=port)
    it.run_command("/go", format="../../evil")
    assert not port.files
    assert any("formato" in str(e) for e in it.events)


def test_export_senza_output_evento_e_no_op(tmp_path):
    k = _mini(
        tmp_path,
        "commands:\n  /go:\n    action: [{export: json}]\n",
    )
    port = FakeExportPort()
    it = Interpreter(k, export_port=port)
    it.run_command("/go")
    assert not port.files
    assert any("senza_output" in str(e) for e in it.events)


def test_export_contatore_deterministico_tra_comandi(tmp_path):
    k = _mini(
        tmp_path,
        "commands:\n  /a:\n    action:\n"
        "      - output: doc a\n      - export: json\n"
        "  /b:\n    action:\n"
        "      - output: doc b\n      - export: md\n",
    )
    port = FakeExportPort()
    it = Interpreter(k, export_port=port)
    it.run_command("/a")
    it.run_command("/b")
    assert sorted(port.files) == ["export_1.json", "export_2.md"]


def test_export_dir_port_scrive_su_disco(tmp_path, monkeypatch):
    # ADR 010: ExportDirPort reale — scrittura atomica, env override,
    # rilettura del contatore dalla directory: una seconda istanza NON
    # riparte da export_1 (review Codex P1 #555 giro 1)
    from src.dsl.store import ExportDirPort

    target = tmp_path / "out"
    monkeypatch.setenv("MASTERS_DD_EXPORTS_PATH", str(target))
    p = ExportDirPort()
    assert p.write("json", '{"a": 1}') == "export_1.json"
    assert (target / "export_1.json").read_text(encoding="utf-8") == '{"a": 1}'
    # istanza nuova, stessa directory: il contatore deriva dai file
    assert ExportDirPort().write("md", "x") == "export_2.md"
    assert (target / "export_2.md").exists()
    assert (target / "export_1.json").exists()  # nessuna sovrascrittura


# ---- Namespace comandi: collisioni rendicontate (ADR 011) ----


def test_loader_rendiconda_shadowed_e_vince_ultimo(tmp_path):
    # ADR 011: la sovrascrittura silenziosa diventa ispezionabile —
    # shadowed[name] = origini in ordine di caricamento, vincitore ultimo
    (tmp_path / "aaa_mod.txt").write_text(
        "commands:\n  /go: {action: [{output: da aaa}]}\n", encoding="utf-8"
    )
    (tmp_path / "zzz_mod.txt").write_text(
        "commands:\n  /go: {action: [{output: da zzz}]}\n", encoding="utf-8"
    )
    k = load_kernel(tmp_path)
    assert k.commands["/go"]["origin"] == "zzz_mod.txt"
    assert k.shadowed == {"/go": ["aaa_mod.txt", "zzz_mod.txt"]}


def test_loader_niente_shadowed_senza_collisioni(tmp_path):
    (tmp_path / "uno.txt").write_text(
        "commands:\n  /a: {action: [{output: x}]}\n", encoding="utf-8"
    )
    (tmp_path / "due.txt").write_text(
        "commands:\n  /b: {action: [{output: y}]}\n", encoding="utf-8"
    )
    k = load_kernel(tmp_path)
    assert k.shadowed == {}


def test_censimento_collisioni_moduli_reali(kernel):
    # ADR 011: censimento 2026-10-27 — 22 nomi in collisione su 12 moduli.
    # Chi cura una collisione (rename authoring) aggiorna questo test
    # consapevolmente: il numero e' un gate, non un accidente.
    assert len(kernel.shadowed) == 22
    for nome in ("/update_build", "/status", "/explain_rule", "/export_vtt"):
        assert nome in kernel.shadowed
    # il vincitore e' sempre l'ultima origine della lista (ordine di load)
    for nome, origini in kernel.shadowed.items():
        assert kernel.commands[nome]["origin"] == origini[-1]


def test_coverage_report_espose_shadowed(kernel):
    # ADR 011: i gate G2 vedono le collisioni, mai silenziose
    report = Interpreter(kernel).coverage_report()
    assert len(report["shadowed"]) == 22
    assert "/update_build" in report["shadowed"]


# ---- goto_state eseguibile (ADR 012) -------------------------------------

GOTO_MINI = """\
state_machine:
  states: [IDLE, QUIZ, READY]
  transitions: []
  GameMode:
    TestWiz:
      start: {prompt: "Scegli: 1/2", parse: {"1": {set: x, value: a}}, next: end}
commands:
  /go_quiz: {action: [{goto_state: QUIZ}]}
  /go_bad: {action: [{goto_state: BOGUS}]}
  /go_wiz: {action: [{goto_state: GameMode.TestWiz.start}]}
  /go_badwiz: {action: [{goto_state: GameMode.Nope.start}]}
  /go_empty: {action: [{goto_state: ""}]}
"""


def test_goto_state_flat_scrive_runtime_current_state(tmp_path):
    it = Interpreter(_mini(tmp_path, GOTO_MINI))
    it.run_command("/go_quiz")
    assert get_path(it.state, "runtime.current_state") == "QUIZ"
    assert it.events == []


def test_goto_state_flat_non_valido_evento_e_nessuna_scrittura(tmp_path):
    it = Interpreter(_mini(tmp_path, GOTO_MINI))
    it.run_command("/go_bad")
    assert get_path(it.state, "runtime.current_state") is None
    assert [e.get("stato_non_valido") for e in it.events] == ["BOGUS"]


def test_goto_state_wizard_scrive_e_emette_prompt(tmp_path):
    it = Interpreter(_mini(tmp_path, GOTO_MINI))
    it.run_command("/go_wiz")
    assert get_path(it.state, "runtime.current_state") == "GameMode.TestWiz.start"
    assert it.output_log == ["Scegli: 1/2"]


def test_goto_state_wizard_primo_segmento_sconosciuto(tmp_path):
    it = Interpreter(_mini(tmp_path, GOTO_MINI))
    it.run_command("/go_badwiz")
    assert get_path(it.state, "runtime.current_state") is None
    assert [e.get("stato_non_valido") for e in it.events] == ["GameMode.Nope.start"]


def test_goto_state_target_vuoto_evento(tmp_path):
    it = Interpreter(_mini(tmp_path, GOTO_MINI))
    it.run_command("/go_empty")
    assert it.events and all("stato_non_valido" in e for e in it.events)


def test_goto_state_moduli_reali(kernel: Kernel):
    # ADR 012 pin: /play_game (Taverna_NPC) fa goto wizard con prompt
    it = Interpreter(kernel)
    it.run_command("/play_game")
    assert (
        get_path(it.state, "runtime.current_state") == "GameMode.OnboardingTheme.lang"
    )
    assert any("Scegli lingua" in o for o in it.output_log)


# ---- Verbi dominio: zucchero su helper omonimi (ADR 013) ----------------

DOMAIN_MINI = """\
helpers:
  compute_xp_budget_estimate:
    params: [party_level, party_size]
    logic: |
      return int(party_level) * int(party_size)
commands:
  /enc:
    params: [lvl]
    action:
      - compute_xp_budget_estimate:
          {party_level: "{{lvl}}", party_size: "4", as: xp}
      - output: "XP={{xp}}"
  /enc_noas:
    action:
      - compute_xp_budget_estimate: {party_level: "2", party_size: "3"}
  /enc_unbound:
    params: [mancante]
    action:
      - compute_xp_budget_estimate:
          {party_level: "{{mancante}}", party_size: "4", as: xp}
  /auto:
    action:
      - generate_enemies_from_biome: {biome: x, as: suggeriti}
  /inp:
    action:
      - {input: "x"}
"""


def test_domain_verb_chiama_helper_omonimo(tmp_path):
    it = Interpreter(_mini(tmp_path, DOMAIN_MINI))
    it.run_command("/enc", lvl=3)
    # MEDIA-8: lo scratch di un comando non tracima — il risultato si
    # dimostra nell'output renderizzato nel comando stesso
    assert it.output_log == ["XP=12"]


def test_domain_verb_senza_as_non_scrive_scratch(tmp_path):
    it = Interpreter(_mini(tmp_path, DOMAIN_MINI))
    it.run_command("/enc_noas")
    assert it.noop_log == []
    assert "xp" not in it.scratch


def test_domain_verb_param_non_legato_no_op(tmp_path):
    # ADR 008: param non legato -> il verbo e' no-op, mai un None fabbricato
    it = Interpreter(_mini(tmp_path, DOMAIN_MINI))
    it.run_command("/enc_unbound")
    assert "xp" not in it.scratch


def test_verbo_senza_helper_motivo_non_implementato(tmp_path):
    it = Interpreter(_mini(tmp_path, DOMAIN_MINI))
    it.run_command("/auto")
    assert it.noop_log == [
        {"verb": "generate_enemies_from_biome", "reason": "non_implementato"}
    ]


def test_input_rimosso_da_no_op_rumoreso(tmp_path):
    # ADR 013: `input` fuori da NO_OP — un uso come verbo e' "?" rumoroso,
    # mai swallowing silenzioso
    it = Interpreter(_mini(tmp_path, DOMAIN_MINI))
    it.run_command("/inp")
    assert it.noop_log and it.noop_log[0]["verb"] == "?"


def test_domain_verb_moduli_reali(tmp_path):
    # ADR 013 pin: /auto_balance (Encounter_Designer) — XP = 100*lvl*size*mult
    k = load_kernel(MODULES, only=("Encounter_Designer.txt",))
    it = Interpreter(k)
    it.state["encounter_state"] = {
        "party": {"average_level": 5, "size": 4, "rules": {}},
        "difficulty": {"target": "Moderate"},
        "enemies": [],
    }
    it.run_command("/auto_balance")
    snap = it.state["encounter_state"]["balance_snapshot"]
    assert snap["xp_budget_est"] == 2000
    assert snap["labels"] == ["unrated"]


def test_domain_verb_risolve_bare_ref_a_oggetto_stato(tmp_path):
    # Codex P2 (#558): in_list: loot_state.inventory e' una ref nuda —
    # l'helper deve ricevere la LISTA viva (e mutarla), non la stringa
    mini = """\
helpers:
  find_and_update_item:
    params: [in_list, filter, set]
    logic: |
      items = in_list or []
      key, val = (filter or {}).get("by"), str((filter or {}).get("value"))
      for it in items:
        if str(it.get(key)) == val:
          for k, v in (set or {}).items():
            it[k] = v
          return True
      return False
commands:
  /tagga:
    params: [nome]
    action:
      - find_and_update_item:
          {in_list: loot_state.inventory, filter: {by: name, value: "{{nome}}"}, set: {tagged: true}, as: ok}
      - output: "ok={{ok}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.state["loot_state"]["inventory"] = [{"name": "spada", "tagged": False}]
    it.run_command("/tagga", nome="spada")
    assert it.state["loot_state"]["inventory"][0]["tagged"] is True
    assert it.output_log == ["ok=True"]


# ---- Wizard input routing (ADR 014) ------------------------------------

WIZARD_MINI = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared:
      profile: {name: "", lang: ""}
    Test:
      entry:
        prompt: "Nome?"
        parse:
          any: {set: "@GameMode.shared.profile.name", value: "{{input}}"}
        next: lang
      lang:
        prompt: "Lingua 1/2?"
        parse:
          "1": {set: "@GameMode.shared.profile.lang", value: "fr"}
          "2": {set: "@GameMode.shared.profile.lang", value: "en"}
          regex: "^(it|en)$"
          groups: [lingua]
          any: {set: "@GameMode.shared.profile.lang", value: "{{input}}"}
        actions:
          # sulla via regex il group lingua e' legato; sulle via map/any
          # e' non-legato -> set no-op ADR 008 (lang gia' scritto)
          - set: "@GameMode.shared.profile.lang"
            value: "{{lingua}}"
        guards:
          - condition: "{{ GameMode.shared.profile.lang != 'xx' }}"
            on_fail: "lingua vietata"
        next: done
      done:
        actions:
          - output: "Fatto {{GameMode.shared.profile.name}}"
        end: true
commands:
  /start: {action: [{goto_state: GameMode.Test.entry}]}
  /status: {action: [{output: "stato ok"}]}
"""


def _wiz(tmp_path) -> Interpreter:
    it = Interpreter(_mini(tmp_path, WIZARD_MINI))
    it.run_command("/start")
    return it


def test_run_input_any_e_avanza_con_prompt(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("Grog")
    assert get_path(it.state, "game_mode.shared.profile.name") == "Grog"
    assert get_path(it.state, "runtime.current_state") == "GameMode.Test.lang"
    assert it.output_log[-1] == "Lingua 1/2?"


def test_run_input_map_esatta_vince_su_regex(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("Grog")
    it.run_input("2")
    assert get_path(it.state, "game_mode.shared.profile.lang") == "en"


def test_run_input_regex_e_groups(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("Grog")
    it.run_input("it")  # regex ^(it|en)$ -> groups[lingua], map non matcha
    assert get_path(it.state, "game_mode.shared.profile.lang") == "it"


def test_run_input_guard_fallito_rimane_sul_nodo(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("Grog")
    it.run_input("xx")  # any lo scrive, guard lo rifiuta -> stay
    assert get_path(it.state, "runtime.current_state") == "GameMode.Test.lang"
    assert it.output_log[-1] == "lingua vietata"


def test_run_input_end_ripristina_idle(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("Grog")
    it.run_input("2")
    assert get_path(it.state, "runtime.current_state") == "IDLE"
    assert it.output_log[-1] == "Fatto Grog"


def test_run_input_senza_wizard_evento(tmp_path):
    it = Interpreter(_mini(tmp_path, WIZARD_MINI))
    it.run_input("ciao")
    assert [e.get("input_fuori_wizard") for e in it.events] == ["ciao"]


def test_run_input_comando_vince_sul_nodo(tmp_path):
    it = _wiz(tmp_path)
    it.run_input("/status")
    assert it.output_log[-1] == "stato ok"
    # il wizard non ha consumato l'input: si resta sul nodo entry
    assert get_path(it.state, "runtime.current_state") == "GameMode.Test.entry"


def test_run_input_modulo_reale_play_game(tmp_path):
    # ADR 014 pin: /play_game poi "3" -> lang=it (map), prompt universo
    k = load_kernel(MODULES, only=("Taverna_NPC.txt",))
    it = Interpreter(k)
    it.run_command("/play_game")
    it.run_input("3")
    assert get_path(it.state, "game_mode.shared.profile.lang") == "it"
    assert get_path(it.state, "runtime.current_state") == (
        "GameMode.OnboardingTheme.universe"
    )
    assert any("Scegli universo" in o for o in it.output_log)


def test_run_input_yes_no_lega_boolean(tmp_path):
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {portrait_done: false}
    T:
      p:
        prompt: "Ritratto?"
        parse:
          yes_no: {key: gen}
        actions:
          - if: "{{gen}}"
            then:
              - set: "@GameMode.shared.portrait_done"
                value: true
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("sì")
    assert get_path(it.state, "game_mode.shared.portrait_done") is True
    assert get_path(it.state, "runtime.current_state") == "IDLE"


def test_run_input_end_action_vince_su_next(tmp_path):
    # Codex P2 #559: un'action `- end: true` chiude il wizard; il next
    # del nodo NON riapre il flusso (pattern Chase.turn)
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      loop:
        prompt: "Turno"
        parse:
          any: {set: risposta, value: "{{input}}"}
        actions:
          - if: '{{ risposta == "fine" }}'
            then:
              - end: true
        next: loop
commands:
  /s: {action: [{goto_state: GameMode.T.loop}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("fine")
    assert get_path(it.state, "runtime.current_state") == "IDLE"
    it.run_input("ancora")  # fuori wizard: evento, nessun prompt turno
    assert [e.get("input_fuori_wizard") for e in it.events] == ["ancora"]


def test_run_input_action_only_avanza(tmp_path):
    # Codex P1 #559 giro 2: nodo senza prompt (solo actions+next) esegue
    # le actions all'arrivo e avanza subito — il flusso non si parchereggia
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      start:
        prompt: "Parti?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        next: setup
      setup:
        actions:
          - set: "@GameMode.shared.ready"
            value: true
        next: nome
      nome:
        prompt: "Come ti chiami?"
        parse:
          any: {set: nome, value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.start}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("vai")
    assert get_path(it.state, "game_mode.shared.ready") is True
    assert get_path(it.state, "runtime.current_state") == "GameMode.T.nome"
    assert it.output_log[-1] == "Come ti chiami?"


def test_run_input_foreach_legge_params_parse(tmp_path):
    # Codex P2 #559 giro 2: any_list lega in params; foreach con nome nudo
    # risolve il binding del parse, non solo scratch/stato/kernel
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      items:
        prompt: "Cosa prendi?"
        parse:
          any_list: {as: items, sep: ","}
        actions:
          - foreach: items
            loop_as: it
            actions:
              - set: "@GameMode.shared.last"
                value: "{{it}}"
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.items}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("spada, scudo")
    assert get_path(it.state, "game_mode.shared.last") == "scudo"
    assert not [e for e in it.events if "foreach_non_risolto" in e]


def test_run_input_command_params_dichiarati_vincolati(tmp_path):
    # Codex P2 #559 giro 2 (end-to-end): i params dichiarati su `command:`
    # erano ignorati — il comando girava con i declared unbound
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      items:
        prompt: "Cosa prendi?"
        parse:
          any_list: {as: items, sep: ","}
        actions:
          - foreach: items
            loop_as: it
            actions:
              - command: /add_item
                params:
                  oggetto: "{{it | trim}}"
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.items}]}
  /add_item:
    params: [oggetto]
    action:
      - set: inventario
        value: "{{ (inventario or []) + [oggetto] }}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("spada, scudo")
    assert it.state.get("inventario") == ["spada", "scudo"]


def test_run_input_slash_command_con_argomenti(tmp_path):
    # Codex P2 #559 giro 3: durante il wizard, /comando arg=val instrada
    # l'input intero — gli argomenti non si scartano dopo il nome
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      p:
        prompt: "Fermo?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
  /add_item:
    params: [oggetto]
    action:
      - set: inventario
        value: "{{ (inventario or []) + [oggetto] }}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("/add_item oggetto=spada")
    assert it.state.get("inventario") == ["spada"]
    assert get_path(it.state, "runtime.current_state") == "GameMode.T.p"


def test_run_input_command_params_omessi_non_legano_none(tmp_path):
    # Codex P2 #559 giro 4: params action che referenziano un param del
    # chiamante omesso si omettono — il None reso aggirerebbe la protezione
    # unbound del comando nested (wipe silenzioso di existing)
    mini = """\
state_machine:
  states: [IDLE]
commands:
  /outer: {action: [{command: /inner, params: {value: "{{missing}}"}}]}
  /inner:
    params: [value]
    action:
      - set: existing
        value: "{{value}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.state["existing"] = "salvato"
    it.run_command("/outer")
    assert it.state["existing"] == "salvato"
    assert any("param:value" in s for s in it._saltati) or [
        e for e in it.events if "update_parziale" in e
    ]


def test_run_input_parse_entry_guardata_non_consuma(tmp_path):
    # Codex P2 #559 giro 4: entry map esatta con when falsa non accettata —
    # il match continua e il catch-all any consuma l'input
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      p:
        prompt: "Scelta?"
        parse:
          segreta:
            when: "{{ false }}"
            set: "@GameMode.shared.hit"
            value: true
          any: {set: "@GameMode.shared.preso", value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("segreta")
    assert get_path(it.state, "game_mode.shared.hit") is None
    assert get_path(it.state, "game_mode.shared.preso") == "segreta"


def test_run_input_command_params_game_mode_alias_e_omesso(tmp_path):
    # Codex P2 #559 giro 5: '@GameMode.' normalizzato anche nell'analisi
    # dei ref — sennò il parse fallisce, espone zero refs e il None reso
    # aggira la protezione unbound del comando nested
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {suffix: ok}
commands:
  /outer: {action: [{command: /inner, params: {value: "{{ missing }}{{ @GameMode.shared.suffix }}"}}]}
  /inner:
    params: [value]
    action:
      - set: existing
        value: "{{value}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.state["existing"] = "salvato"
    it.run_command("/outer")
    assert it.state["existing"] == "salvato"


def test_run_input_command_params_game_mode_alias_sano(tmp_path):
    # controllo: params SOLO @GameMode. (senza nomi omessi) NON si droppa
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {money_gp: 25}
commands:
  /outer: {action: [{command: /inner, params: {value: "{{ @GameMode.shared.money_gp }}"}}]}
  /inner:
    params: [value]
    action:
      - set: existing
        value: "{{value}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/outer")
    assert it.state["existing"] == 25


def test_run_input_parse_entry_guardata_vera_esegue_sibling(tmp_path):
    # Codex P2 #559 giro 6: when vero tolto prima del dispatch — sennò
    # _dispatch invocherebbe _v_when e il sibling set saltava (ordine YAML)
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      p:
        prompt: "Scelta?"
        parse:
          accetta:
            when: "{{ true }}"
            set: "@GameMode.shared.accepted"
            value: true
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("accetta")
    assert get_path(it.state, "game_mode.shared.accepted") is True


def test_run_input_slash_utente_mai_renderizzato(tmp_path):
    # Codex P1 #559 giro 7: l'input slash utente NON passa da _rn —
    # Jinja non sandboxed non e' esposta all'input (RCE via template)
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      p:
        prompt: "Fermo?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
  /segna:
    params: [val]
    action:
      - set: preso
        value: "{{val}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input('/segna val="{{ 7 * 7 }}"')
    assert it.state.get("preso") == "{{ 7 * 7 }}"  # letterale, non 49
    assert get_path(it.state, "runtime.current_state") == "GameMode.T.p"


def test_goto_su_action_only_esegue_e_avanza(tmp_path):
    # Codex P2 #559 giro 7: goto_state su nodo senza prompt (Chase.entry,
    # Gambling) — le actions girano all'arrivo e si avanza al nodo
    # interattivo, non si resta parcheggiati senza parser
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      entry:
        actions:
          - set: "@GameMode.shared.entrato"
            value: true
        next: turno
      turno:
        prompt: "Turno 1?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /chase_start: {action: [{goto_state: GameMode.T.entry}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/chase_start")
    assert get_path(it.state, "game_mode.shared.entrato") is True
    assert get_path(it.state, "runtime.current_state") == "GameMode.T.turno"
    assert it.output_log[-1] == "Turno 1?"


def test_run_input_slash_quoting_malformato_evento_non_crash(tmp_path):
    # Codex P2 #559 giro 8: quoting malformato nell'input utente -> evento
    # diagnostico e si resta sul nodo, mai ValueError all'host
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      p:
        prompt: "Fermo?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.p}]}
  /segna:
    params: [val]
    action:
      - set: preso
        value: "{{val}}"
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input('/segna val="spada')  # quote non chiusa
    assert [e for e in it.events if "tokenizzazione_fallita" in e]
    assert get_path(it.state, "runtime.current_state") == "GameMode.T.p"
    assert it.state.get("preso") is None


def test_run_input_next_valuta_guard_tema_genitore(tmp_path):
    # Codex P2 #559 giro 8: next che entra in un tema con when falso sul
    # TEMA (non sul nodo) -> wizard_guard_falso, nessuna esecuzione
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      start:
        prompt: "Vai?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        next: "@GameMode.K.entry"
    K:
      when: "{{ false }}"
      entry:
        actions:
          - set: "@GameMode.shared.fatto"
            value: true
        prompt: "Tema guardato?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /s: {action: [{goto_state: GameMode.T.start}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/s")
    it.run_input("vai")
    assert [e for e in it.events if "wizard_guard_falso" in e]
    assert get_path(it.state, "game_mode.shared.fatto") is None


def test_goto_action_only_rispetta_guard_tema(tmp_path):
    # Codex P2 #559 giro 9: goto_state su nodo action-only di un tema con
    # when falso — guard valutato PRIMA delle arrival actions
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    K:
      when: "{{ false }}"
      entry:
        actions:
          - set: "@GameMode.shared.fatto"
            value: true
        next: p
      p:
        prompt: "?"
        parse:
          any: {set: risposta, value: "{{input}}"}
        end: true
commands:
  /go: {action: [{goto_state: GameMode.K.entry}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/go")
    assert [e for e in it.events if "wizard_guard_falso" in e]
    assert get_path(it.state, "game_mode.shared.fatto") is None


def test_goto_self_action_only_bounded(tmp_path):
    # Codex P2 #559 giro 9: self-goto su nodo action-only — depth cresce,
    # evento diagnostico, mai RecursionError
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    T:
      loop:
        actions:
          - set: "@GameMode.shared.n"
            value: "{{ (game_mode.shared.n or 0) + 1 }}"
          - goto_state: GameMode.T.loop
commands:
  /go: {action: [{goto_state: GameMode.T.loop}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/go")
    assert [e for e in it.events if "avanzamento_profondita_max" in e]


def test_goto_interattivo_rispetta_guard_tema(tmp_path):
    # Codex P2 #559 giro 10: goto su nodo CON prompt sotto tema guardato —
    # guard valutato prima di atterrare, nessuna action del nodo
    mini = """\
state_machine:
  states: [IDLE]
  GameMode:
    shared: {}
    K:
      when: "{{ false }}"
      p:
        prompt: "Tema guardato?"
        parse:
          any: {set: "@GameMode.shared.accepted", value: true}
        end: true
commands:
  /go: {action: [{goto_state: GameMode.K.p}]}
"""
    it = Interpreter(_mini(tmp_path, mini))
    it.run_command("/go")
    assert [e for e in it.events if "wizard_guard_falso" in e]
    assert get_path(it.state, "game_mode.shared.accepted") is None
    assert (
        get_path(it.state, "runtime.current_state") != "GameMode.K.p"
    )  # mai atterrato


# ---- Router input libero (ADR 015, ES4) --------------------------------

# raw string: i pattern regex con \b restano letterali fino a re
_ROUTER_MINI = r"""
router:
  intent_detection:
    normalize: {lowercase: true, strip_punct: true, fold_accents: true, regex_flags: "i"}
    segmenter:
      enabled: true
      split_regex: '(?:,?\s*(?:e poi|poi|quindi|;)\s+)'
      per_segment_routing: true
      merge_same_module: true
  rules:
    - match: ['^/help\b']
      route_to: "Documentazione"
      short_circuit: true
    - match_any:
        - '\b(talento|feat|regola)\b'
        - '\btwo[- ]weapon fighting\b'
      not_match: ['\b(storia)\b']
      route_to: "Ruling Expert"
    - match_any:
        - '\b(storia|golarion)\b'
      route_to: "Archivist"
    - match_any:
        - '\b(npc|quiz)\b'
      embedding: true
      rerank: true
      route_to: "Taverna NPC"
    - condition: "runtime.intent_candidates && runtime.intent_candidates.length > 1"
      after_segments: true
      reply: "Quale modulo?"
      stop: true
    - fallback: "Ruling Expert"
  fallback_policy:
    multi_match: "ask_clarification"
    no_match: "Ruling Expert"
    clarification_prompt: "Dimmi il tuo intento."
  decorators:
    pre_routing:
      - if: "!runtime.preload_done"
        then:
          - invoke: "orchestration.pipeline.Preload_Warmup"
          - set: [runtime.preload_done: true]
    post_routing:
      - if: "route_to"
        then:
          - set: [runtime.mode_attivo: "{{ route_to }}"]
"""


def test_route_input_match_regex(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    rt = it.route_input("cosa fa il talento Pounce?")
    assert rt == "Ruling Expert"
    assert get_path(it.state, "runtime.route_to") == "Ruling Expert"
    assert get_path(it.state, "runtime.mode_attivo") == "Ruling Expert"


def test_route_input_short_circuit_primo_vince(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("/help qualcosa") == "Documentazione"


def test_route_input_not_match_esclude(tmp_path):
    # 'storia' matcha Archivist; la regola Ruling ha not_match su 'storia'
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("parlami della storia di Golarion") == "Archivist"


def test_route_input_normalize_accenti_e_maiuscole(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("TALENTO Àèì") == "Ruling Expert"


def test_route_input_multi_match_chiede_chiarimento(tmp_path):
    # 'talento' + 'npc': due moduli diversi -> clarification, niente route
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("talento npc") is None
    assert "Quale modulo?" in it.output_log
    assert "Dimmi il tuo intento." not in it.output_log  # una sola reply (g4)
    cands = get_path(it.state, "runtime.intent_candidates")
    assert set(cands) == {"Ruling Expert", "Taverna NPC"}


def test_route_input_fallback_no_match(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("xyzzy pinco pallino") == "Ruling Expert"


def test_route_input_embedding_rerank_noop_log(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("genera npc") == "Taverna NPC"
    assert any(
        n.get("reason") == "pipeline_non_implementata"
        for n in it.noop_log
        if n.get("verb") in ("embedding", "rerank")
    )


def test_route_input_invoke_noop_pipeline(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    it.route_input("cosa fa il talento Pounce?")
    assert any(
        n.get("verb") == "invoke" and n.get("reason") == "pipeline_non_implementata"
        for n in it.noop_log
    )
    # i set dei decorators invece si applicano
    assert get_path(it.state, "runtime.preload_done") is True


def test_route_input_segmenter_merge_stesso_modulo(tmp_path):
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    rt = it.route_input("spiegami il talento Pounce; poi una regola")
    assert rt == "Ruling Expert"
    cands = get_path(it.state, "runtime.intent_candidates")
    assert cands == ["Ruling Expert"]


def test_route_input_condition_sintassi_authored(tmp_path):
    # '!' tradotto: la condition authored non e' falsa per sintassi — la
    # rule non matcha il regex ma non deve neanche dichiarare l'evento
    mini = _ROUTER_MINI.replace(
        '- condition: "runtime.intent_candidates && runtime.intent_candidates.length > 1"',
        '- condition: "!runtime.preload_done"\n'
        "      match: ['^__mai__']\n"
        "      continue: true",
    )
    it = Interpreter(_mini(tmp_path, mini))
    it.route_input("talento")
    assert not [e for e in it.events if "condizione" in str(e)]


def test_route_input_condition_falsa_valutata(tmp_path):
    # Codex P1 #560: condition bare valutata come ESPRESSIONE ({{ }}), non
    # truthy di una stringa non vuota — decorator condizionale non scatta
    mini = _ROUTER_MINI.replace(
        """    post_routing:
      - if: "route_to"
        then:
          - set: [runtime.mode_attivo: "{{ route_to }}"]""",
        """    post_routing:
      - if: "route_to"
        then:
          - set: [runtime.mode_attivo: "{{ route_to }}"]
      - if: "route_to == 'Archivist'"
        then:
          - set: [runtime.solo_archivist: true]""",
    )
    it = Interpreter(_mini(tmp_path, mini))
    assert it.route_input("talento Pounce") == "Ruling Expert"
    assert get_path(it.state, "runtime.mode_attivo") == "Ruling Expert"
    assert get_path(it.state, "runtime.solo_archivist") is None
    it.route_input("storia di Absalom")
    assert get_path(it.state, "runtime.solo_archivist") is True


def test_route_input_fallback_solo_a_candidato_zero(tmp_path):
    # Codex P2 #560: un match unico NON diventa multi-match col fallback
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("genera npc") == "Taverna NPC"
    assert get_path(it.state, "runtime.intent_candidates") == ["Taverna NPC"]
    assert "Dimmi il tuo intento." not in it.output_log


def test_route_input_disambiguazione_vede_candidati_correnti(tmp_path):
    # Codex P2 #560: la rule disambiguazione legge i candidati del turno
    # corrente (non quelli precedenti) nel reply
    mini = _ROUTER_MINI.replace(
        'reply: "Quale modulo?"',
        "reply: \"Candidati: {{ runtime.intent_candidates | join(', ') }}\"",
    )
    it = Interpreter(_mini(tmp_path, mini))
    assert it.route_input("talento npc") is None
    assert "Candidati: Ruling Expert, Taverna NPC" in it.output_log
    it.output_log.clear()
    assert it.route_input("storia") == "Archivist"
    assert not [o for o in it.output_log if o.startswith("Candidati:")]


def test_route_input_fallback_indipendente_da_ordine_segmenti(tmp_path):
    # Codex P2 #560 g2: il fallback e' default dell'input intero — un
    # segmento non riconosciuto accanto a uno riconosciuto non lo attiva
    # in nessun ordine
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("xyzzy; poi storia di golarion") == "Archivist"
    it2 = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it2.route_input("storia di golarion; poi xyzzy") == "Archivist"


def test_route_input_clarification_resetta_route_to(tmp_path):
    # Codex P2 #560 g2: turno non risolto (clarification) -> route_to
    # azzerato, non resta quello del turno precedente
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("talento Pounce") == "Ruling Expert"
    assert get_path(it.state, "runtime.route_to") == "Ruling Expert"
    assert it.route_input("talento npc") is None
    assert get_path(it.state, "runtime.route_to") is None


def test_route_input_segmenter_rispetta_regex_flags(tmp_path):
    # Codex P2 #560 g3: "POI" maiuscolo deve splittare come "poi" —
    # sennò "/help" short-circuit consuma anche il segmento successivo
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("/HELP POI TALENTO") is None
    assert len(get_path(it.state, "runtime.intent_candidates")) == 2


def test_route_input_strip_punct_pattern_classe_carattere(tmp_path):
    # Codex P2 #560 g3: strip_punct trasforma "two-weapon" in "two weapon" —
    # nei pattern la punteggiatura va data come classe ([- ]), come gia'
    # faceva flat[- ]footed in base_profile.txt
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("spiega il TWO-WEAPON FIGHTING") == "Ruling Expert"


def test_route_input_disambiguazione_dopo_tutti_i_segmenti(tmp_path):
    # Codex P2 #560 g4: la reply disambiguazione va emessa UNA volta sui
    # candidati finali — non una parziale per ogni segmento (input
    # multi-segmento emetteva prompt ripetuti e crescenti)
    it = Interpreter(_mini(tmp_path, _ROUTER_MINI))
    assert it.route_input("storia; poi talento; poi npc") is None
    assert [o for o in it.output_log if o == "Quale modulo?"].count(
        "Quale modulo?"
    ) == 1
    assert len(get_path(it.state, "runtime.intent_candidates")) == 3
