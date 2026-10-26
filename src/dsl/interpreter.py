"""Interprete deterministico dei comandi dei moduli (DSL).

Il modello propone i comandi, l'interprete li esegue: zero LLM qui dentro.
Verbi non eseguibili in ES1 (sessione/flow, dominio, RAG): no-op dichiarati,
registrati in ``noop_log`` — mai silenziosi.
"""

from __future__ import annotations

import copy as _copy
import json
import shlex
import textwrap
from typing import Any

import jinja2
from jinja2.nativetypes import NativeEnvironment

from .loader import Kernel, _safe_import
from .state import get_path, set_path

MAX_DEPTH = 8


def _attr(value: Any, attribute: str) -> Any:
    for part in str(attribute).split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
    return value


def _none_safe(env: Any) -> None:
    """Filtri tolleranti a None: None conta come vuoto (len 0, join "",
    map/su su vuoto) invece di crashare — le condizioni del DSL assumono
    chiavi assenti = collezioni vuote."""

    def length(value: Any) -> int:
        return 0 if value is None else len(value)

    def join(value: Any, sep: str = "", attribute: str = None, **kw: Any) -> str:
        if value is None:
            return ""
        items = (_attr(x, attribute) for x in value) if attribute else value
        return sep.join(str(x) for x in items)

    def map_filter(value: Any = None, *args: Any, **kw: Any) -> Any:
        if value is None:
            return iter(())
        attribute = kw.get("attribute")
        if attribute:
            return (_attr(x, attribute) for x in value)
        return iter(value)  # ponytail: forma con funzione non usata nei moduli

    def sum_filter(value: Any = None, attribute: str = None, **kw: Any) -> Any:
        if value is None:
            return 0
        if attribute:
            value = (_attr(x, attribute) for x in value)
        return sum(value)

    env.filters.update(length=length, count=length, join=join,
                       map=map_filter, sum=sum_filter)


class DslAbort(Exception):
    """abort/error dichiarati nel DSL."""


class LenientUndefined(jinja2.ChainableUndefined):
    """Rende i template degli output tolleranti a chiavi mancanti
    (iterazione vuota, catene e subscript su Undefined) — come il rendering
    mentale del modello: la card si stampa con gli spazi vuoti."""

    def __iter__(self):
        return iter(())

    def __call__(self, *args: Any, **kwargs: Any) -> "LenientUndefined":
        return self

    def __len__(self) -> int:
        return 0

    def __bool__(self) -> bool:
        return False


class _NativeNoneUndefined(jinja2.Undefined):
    """Env native per value/if: nomi liberi sconosciuti restano un errore
    (typo = segnale), ma una chiave mancante su un dict esistente degrada a
    None — nello stato del DSL 'assente' significa 'non ancora valorizzato'."""

    def __getattr__(self, name: str) -> None:
        return None

    def __getitem__(self, key: Any) -> None:
        return None

    def __str__(self) -> str:
        return ""


ESEGUIBILI = frozenset({
    "set", "append", "extend", "clear", "copy", "increment", "update_dict",
    "if", "when", "foreach", "for", "switch", "set_mode",
    "output", "output_template",
    "call", "compute", "command", "call_command", "route",
    "parse_json", "find_in", "guard_all", "error", "abort",
})

# ES1: no-op dichiarati (ES2 = sessione/flow; dominio = ES3; RAG = banco)
NO_OP = frozenset({
    "input", "export", "emit_event", "goto_state", "save_session",
    "load_session", "list_session_keys", "replace_placeholder", "roll",
    "match", "match_any", "invoke", "search_meta_sources",
    "find_in_list", "find_and_consume_item", "find_and_update_item",
    "run_qagates", "cross_reference_class",
    # dominio Encounter_Designer / benchmark (ES3 o mai)
    "generate_enemies_from_biome", "compute_xp_budget_estimate",
    "compute_effective_cr_from_enemies", "classify_balance_label",
    "estimate_party_benchmarks", "estimate_enemy_benchmarks",
    "detect_risks", "build_buylist", "analyze_meta_results",
    "build_risk_heatmap", "build_top_risks",
})

STRUCTURAL = frozenset({
    "value", "with", "then", "else", "actions", "do", "cases", "when",
    "loop_as", "return_as", "as", "to", "from", "where", "equals", "input",
    "key", "append_values", "on_fail", "requires", "passthrough", "by",
    "logic",
})

_BUILTINS = {}


def _builtins() -> dict[str, Any]:
    if not _BUILTINS:
        import builtins

        for name in ("str", "int", "float", "len", "any", "all", "sum",
                     "max", "min", "sorted", "round", "list", "dict", "set",
                     "tuple", "enumerate", "zip", "range", "reversed",
                     "abs", "bool"):
            _BUILTINS[name] = getattr(builtins, name)
    return _BUILTINS


class Interpreter:
    def __init__(self, kernel: Kernel):
        self.kernel = kernel
        self.state: dict[str, Any] = {
            root: {}
            for root in ("build_state", "local", "runtime", "benchmarks",
                         "loot_state", "tavern_state", "encounter_state",
                         "story_state", "doc_state", "qa_result")
        }
        self.scratch: dict[str, Any] = {}
        self.output_log: list[str] = []
        self.noop_log: list[dict[str, str]] = []
        self.events: list[dict[str, Any]] = []
        self._g: dict[str, Any] = {"__import__": _safe_import, **_builtins()}
        self._sync()
        kernel.bind_globals(self._g)
        self._native = NativeEnvironment(undefined=_NativeNoneUndefined)  # value/if
        self._std = jinja2.Environment(undefined=LenientUndefined)  # output
        _none_safe(self._native)
        _none_safe(self._std)
        self._native.globals.update(_builtins())
        self._std.globals.update(_builtins())

    # -- contesto e rendering -------------------------------------------

    def _sync(self) -> None:
        for k, v in self.state.items():
            self._g[k] = v

    def _ctx(self, params: dict[str, Any], output: bool = False) -> dict[str, Any]:
        # i template dei moduli usano le chiavi di build_state e i dati
        # top-level del modulo come nomi liberi ({{step}}, {{meta_reference}}):
        # flatten di stato + dati modulo, poi namespace, scratch, params,
        # helper (questi vincono in ordine crescente di precedenza).
        # Nei render di OUTPUT i None diventano assenti (Undefined clemente):
        # '{% for x in classi %}' con classi=None itera vuoto invece di
        # esplodere. Nei render NATivi i None restano espliciti (D8: il test
        # '{{abp is not none}}' deve vedere None, non Undefined).
        def clean(d: dict) -> dict:
            return {k: v for k, v in d.items() if v is not None} if output else dict(d)

        ctx: dict[str, Any] = {}
        for root in self.state.values():
            if isinstance(root, dict):
                ctx.update(clean(root))
        ctx.update(clean(self.kernel.data))
        ctx.update(self.state)
        ctx.update(clean(self.scratch))
        ctx.update(clean(params))
        ctx.update(self.kernel.helper_funcs(self._g))
        return ctx

    def _rn(self, value: Any, params: dict) -> Any:
        """Render native (value/if/when): bool e int nativi; chiave mancante
        su dict esistente -> None (assente = non valorizzato)."""
        if not isinstance(value, str) or ("{{" not in value and "{%" not in value):
            return value
        result = self._native.from_string(value).render(self._ctx(params))
        return None if isinstance(result, jinja2.Undefined) else result

    def _cond(self, value: Any, params: dict) -> bool:
        """Condizione if/when. Una guardia non parseggiabile (sintassi non
        Jinja nei moduli, es. comprehension python) dichiara un evento e
        valuta falsa: il blocco e' saltato, lo stato non viene mutato."""
        try:
            return bool(self._rn(value, params))
        except jinja2.TemplateSyntaxError as exc:
            self.events.append({"condizione_non_parseggiabile": str(exc)[:120]})
            return False

    def _rs(self, value: Any, params: dict) -> str:
        """Render stringa (output/template): testo invariato."""
        if not isinstance(value, str):
            return str(value)
        return self._std.from_string(value).render(self._ctx(params, output=True))

    def _resolve(self, ref: Any, params: dict) -> Any:
        """Risolve un riferimento: template, poi path nello stato, poi dati modulo."""
        value = self._rn(ref, params)
        if isinstance(value, str) and "." in value:
            found = get_path(self.state, value, None)
            if found is not None:
                return found
            return get_path(self.kernel.data, value, None)
        return value

    # -- esecuzione comandi ----------------------------------------------

    def run_command(self, name: str, **params: Any) -> None:
        cmd = self.kernel.commands.get(name)
        if cmd is None:
            raise DslAbort(f"comando sconosciuto: {name}")
        declared = cmd.get("params") or []
        bound = {p: params.get(p) for p in declared}  # D8: mancanti -> None
        self._run_actions(cmd.get("action") or [], bound, 0)
        self._sync()

    def _run_actions(self, actions: list, params: dict, depth: int) -> None:
        for action in actions or []:
            if not isinstance(action, dict):
                continue
            self._dispatch(action, params, depth)

    def _dispatch(self, a: dict, params: dict, depth: int) -> None:
        verb = next((k for k in a if k in ESEGUIBILI or k in NO_OP), None)
        if verb is None:
            self.noop_log.append({"verb": "?", "raw": str(a)[:120]})
            return
        if verb in NO_OP:
            self.noop_log.append({"verb": verb})
            return
        getattr(self, f"_v_{verb}")(a, params, depth)

    def _v_set(self, a, params, depth):
        target = a["set"]
        if isinstance(target, list):  # flow style: [{path: val}, ...]
            for item in target:
                for path, value in item.items():
                    self._set_target(path, self._rn(value, params))
            return
        self._set_target(target, self._rn(a.get("value"), params))

    def _set_target(self, path: str, value: Any) -> None:
        # set su variabile di loop: "e.stato" muta l'item puntato, non lo stato
        head, _, rest = path.partition(".")
        if rest and isinstance(self.scratch.get(head), dict):
            set_path(self.scratch[head], rest, value)
            return
        set_path(self.state, path, value)

    def _v_append(self, a, params, depth):
        path = a["append"]
        cur = get_path(self.state, path)
        if not isinstance(cur, list):
            cur = []
            set_path(self.state, path, cur)
        cur.append(self._rn(a.get("value"), params))

    def _v_extend(self, a, params, depth):
        path = a["extend"]
        cur = get_path(self.state, path)
        if not isinstance(cur, list):
            cur = []
            set_path(self.state, path, cur)
        value = self._rn(a.get("value"), params)
        cur.extend(value if isinstance(value, list) else [value])

    def _v_clear(self, a, params, depth):
        set_path(self.state, a["clear"], [])

    def _v_copy(self, a, params, depth):
        set_path(self.state, a["to"], _copy.deepcopy(get_path(self.state, a["copy"])))

    def _v_increment(self, a, params, depth):
        path = a["increment"]
        set_path(self.state, path, (get_path(self.state, path) or 0)
                 + int(a.get("by") or 1))

    def _v_update_dict(self, a, params, depth):
        path = a["update_dict"]
        cur = get_path(self.state, path)
        if not isinstance(cur, dict):
            cur = {}
            set_path(self.state, path, cur)
        key = self._rn(a.get("key"), params)
        values = self._rn(a.get("append_values"), params)
        cur.setdefault(key, []).extend(values if isinstance(values, list) else [values])

    def _v_if(self, a, params, depth):
        branch = a.get("then") if self._cond(a["if"], params) else a.get("else")
        self._run_actions(branch or [], params, depth)

    def _v_when(self, a, params, depth):
        if self._cond(a["when"], params):
            self._run_actions(a.get("do") or [], params, depth)

    def _v_foreach(self, a, params, depth):
        items = self._resolve(a["foreach"], params) or []
        loop_as = a.get("loop_as") or "item"
        for item in items:
            self.scratch[loop_as] = item
            self._run_actions(a.get("actions") or [], params, depth)

    def _v_for(self, a, params, depth):
        # forma: for: e in "{{ expr }}"  (+ do:)
        spec = str(a["for"])
        var, _, expr = spec.partition(" in ")
        var = var.strip()
        items = self._resolve(expr.strip(), params) or []
        for item in items:
            self.scratch[var] = item
            self._run_actions(a.get("do") or [], params, depth)

    def _v_set_mode(self, a, params, depth):
        set_path(self.state, "runtime.mode", self._rn(a["set_mode"], params))

    def _v_switch(self, a, params, depth):
        value = self._rn(a["switch"], params)
        for case in a.get("cases") or []:
            if isinstance(case, dict) and str(self._rn(case.get("when"), params)) == str(value):
                self._run_actions(case.get("do") or [], params, depth)
                return

    def _v_output(self, a, params, depth):
        self.output_log.append(self._rs(a.get("output"), params))

    def _v_output_template(self, a, params, depth):
        name = a["output_template"]
        if "{{" in name or "{%" in name:  # template inline, non un nome
            self.output_log.append(self._std.from_string(name).render(self._ctx(params, output=True)))
            return
        tmpl = self.kernel.templates.get(name)
        if tmpl is None:
            raise DslAbort(f"template mancante: {name}")
        self.output_log.append(self._std.from_string(tmpl).render(self._ctx(params, output=True)))

    def _v_call(self, a, params, depth):
        fn = self._g.get(a["call"])
        if not callable(fn):
            self.noop_log.append({"verb": f"call:{a['call']}", "motivo": "helper non compilato"})
            return
        kwargs = {k: self._rn(v, params) for k, v in (a.get("with") or {}).items()}
        result = fn(**kwargs)
        if a.get("return_as"):
            self.scratch[a["return_as"]] = result

    def _v_compute(self, a, params, depth):
        body = (a.get("logic") or "").rstrip()
        src = "def __compute():\n" + textwrap.indent(body, "    ")
        exec(compile(src, "<compute>", "exec"), self._g)
        set_path(self.state, a["compute"], self._g["__compute"]())

    def _v_command(self, a, params, depth):
        self._dispatch_command(a.get("command") or a.get("route")
                               or a.get("call_command"), depth)

    def _v_call_command(self, a, params, depth):
        self._dispatch_command(a.get("call_command") or a.get("command"), depth)

    def _v_route(self, a, params, depth):
        self._dispatch_command(a.get("route"), depth)

    def _dispatch_command(self, spec: Any, depth: int) -> None:
        if depth >= MAX_DEPTH:
            raise DslAbort(f"ricorsione command: oltre profondita {MAX_DEPTH}")
        if not isinstance(spec, str):
            raise DslAbort(f"command non stringa: {spec!r}")
        tokens = shlex.split(spec)
        if not tokens:
            return
        name, kv = tokens[0], {}
        for tok in tokens[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k] = v
        self.run_command(name, **kv)

    def _v_parse_json(self, a, params, depth):
        o = a["parse_json"]
        self.scratch[o["as"]] = json.loads(self._rs(o["input"], params))

    def _v_find_in(self, a, params, depth):
        f = a["find_in"]
        lst = self._resolve(f.get("from"), params) or []
        where = f.get("where") or {}
        equals = self._rn(where.get("equals"), params)
        found = next((it for it in lst
                      if isinstance(it, dict) and it.get(where.get("field")) == equals), None)
        self.scratch[f["as"]] = found

    def _v_guard_all(self, a, params, depth):
        g = a["guard_all"] or {}
        if not get_path(self.state, g.get("requires") or ""):
            self.events.append({"guard_fail": g.get("on_fail")})

    def _v_error(self, a, params, depth):
        raise DslAbort(self._rs(a.get("error"), params))

    def _v_abort(self, a, params, depth):
        raise DslAbort(self._rs(a.get("abort") or "abort", params))

    # -- report di copertura (G2) ----------------------------------------

    def coverage_report(self) -> dict[str, Any]:
        report: dict[str, Any] = {"totale": 0, "eseguibile": 0, "no_op": 0,
                                  "no_op_cmds": [], "errore": []}
        for name, cmd in self.kernel.commands.items():
            report["totale"] += 1
            verbs: set[str] = set()
            self._collect_verbs(cmd.get("action") or [], verbs)
            unknown = verbs - ESEGUIBILI - NO_OP
            missing_tmpl = [t for t in self._templates_in(cmd.get("action") or [])
                            if t not in self.kernel.templates]
            if unknown or missing_tmpl:
                report["errore"].append(
                    {"comando": name, "verbi_sconosciuti": sorted(unknown),
                     "template_mancanti": missing_tmpl, "origin": cmd.get("origin")})
            elif verbs & NO_OP:
                report["no_op"] += 1
                report["no_op_cmds"].append(name)
            else:
                report["eseguibile"] += 1
        return report

    def _collect_verbs(self, actions: list, verbs: set) -> None:
        for action in actions or []:
            if not isinstance(action, dict):
                continue
            for key in action:
                if key in ESEGUIBILI or key in NO_OP:
                    verbs.add(key)
                elif key not in STRUCTURAL:
                    verbs.add(key)  # candidato sconosciuto: la classificazione lo rivela
            for key in ("then", "else", "actions", "do"):
                if isinstance(action.get(key), list):
                    self._collect_verbs(action[key], verbs)
            for case in action.get("cases") or []:
                if isinstance(case, dict) and isinstance(case.get("do"), list):
                    self._collect_verbs(case["do"], verbs)

    def _templates_in(self, actions: list) -> list[str]:
        found: list[str] = []
        for action in actions or []:
            if isinstance(action, dict):
                name = action.get("output_template")
                if isinstance(name, str) and "{{" not in name and "{%" not in name:
                    found.append(name)
                for key in ("then", "else", "actions", "do"):
                    if isinstance(action.get(key), list):
                        found.extend(self._templates_in(action[key]))
        return found
