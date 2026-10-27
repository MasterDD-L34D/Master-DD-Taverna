"""Interprete deterministico dei comandi dei moduli (DSL).

Il modello propone i comandi, l'interprete li esegue: zero LLM qui dentro.
Verbi non eseguibili in ES1 (sessione/flow, dominio, RAG): no-op dichiarati,
registrati in ``noop_log`` — mai silenziosi.
"""

from __future__ import annotations

import ast
import builtins
import copy as _copy
import json
import re
import shlex
import textwrap
from functools import lru_cache
from typing import Any

import jinja2
from jinja2.meta import find_undeclared_variables
from jinja2.nativetypes import NativeEnvironment
from jinja2.visitor import NodeVisitor

from .loader import DENIED_BUILTINS, Kernel, _safe_import
from .state import _MISSING, get_path, set_path
from .store import EXPORT_EXTENSIONS, ExportDirPort, JsonFilePort

MAX_DEPTH = 8
_MISSING = object()

# ADR 009: chiavi archivio sessione con prefisso dominio (build_/enc_...) —
# il rifiuto e' un evento, mai una sanificazione silenziosa.
SESSION_KEY_RE = re.compile(r"^[a-z]+_[A-Za-z0-9_-]{1,64}$")

_PARSE_ENV = jinja2.Environment()  # solo parse per la scansione dei nomi
# token di una spec comando: sequenze di frammenti non-spaziature, template
# (un template puo' contenere spazi: "count={{ n }}" e' UN token) o argomenti
# quoted interi (anche con spazi: 'text="{{ n }} suffix"' e' UN token).
_SPEC_TOKEN_RE = re.compile(r"(?:\"[^\"]*\"|'[^']*'|\{\{.*?\}\}|\{%.*?%\}|\S)+")


class _ProtectedOccurrences(NodeVisitor):
    """id() dei nodi Name in posizione protetta da fallback esplicito
    (lato sinistro di un `or`, argomento di `default`/`d`): per-OCCORRENZA,
    non per nome — in '{{ n|default("f") }} {{ n }}' solo la prima e'
    protetta, la seconda rende il template misto (Codex P2, review #553
    giro 2). find_all scende solo ai figli: il nodo stesso va aggiunto a mano."""

    def __init__(self) -> None:
        self.protected: set = set()

    def _mark(self, node: Any) -> None:
        if isinstance(node, jinja2.nodes.Name):
            self.protected.add(id(node))
        for nm in node.find_all(jinja2.nodes.Name):
            self.protected.add(id(nm))

    def visit_Or(self, node: Any) -> None:
        # lato sinistro di un 'or': se rende falsy (None) si prende il dx
        self._mark(node.left)
        self.generic_visit(node)

    def visit_Filter(self, node: Any) -> None:
        if node.name in ("default", "d"):
            self._mark(node.node)
        self.generic_visit(node)


@lru_cache(maxsize=None)
def _tmpl_exposed(tmpl: str) -> frozenset:
    """Nomi liberi (scope-aware: find_undeclared_variables esclude le
    variabili bound da for/set interni al template) con ALMENO un'occorrenza
    SENZA fallback (or/default): su questi un nome non legato e' un wipe.
    I nomi con tutte le occorrenze protette restano fuori: il render li
    risolve da solo (None e' falsy: 'n or X' prende X) senza wipe (idioma
    Codex P2: '/inner count={{ n or 3 }}'). Non parseggiabile -> insieme
    vuoto: la scansione non salta mai per un refuso di sintassi (lo
    segnalano i gate G3/static_check)."""
    try:
        parsed = _PARSE_ENV.parse(tmpl)
    except jinja2.TemplateSyntaxError:
        return frozenset()
    liberi = find_undeclared_variables(parsed)
    prot = _ProtectedOccurrences()
    prot.visit(parsed)
    return frozenset(
        nm.name
        for nm in parsed.find_all(jinja2.nodes.Name)
        if nm.name in liberi and id(nm) not in prot.protected
    )


def _is_named_arg(tok: str) -> bool:
    """True se il token e' un argomento named (k=v): l'assegnamento si
    riconosce solo FUORI dalle espressioni template — '{{ n == 1 }}' e'
    posizionale (Codex P2, review PR #553 giro 3)."""
    return "=" in re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", tok)


def _referenced_vars(node: Any) -> set:
    """Nomi liberi senza fallback referenziati da un nodo YAML, ricorsivo
    su dict/liste."""
    out: set = set()
    if isinstance(node, str):
        if "{{" in node or "{%" in node:
            # Codex P2 #559 giro 5: normalizzato l'alias come in _rn —
            # sennò '@GameMode.' e' errore di parse, espone zero refs e
            # il None reso aggira la protezione unbound
            out |= _tmpl_exposed(node.replace("@GameMode.", "GameMode."))
    elif isinstance(node, dict):
        for v in node.values():
            out |= _referenced_vars(v)
    elif isinstance(node, list):
        for v in node:
            out |= _referenced_vars(v)
    return out


def _as_list(node: Any) -> list:
    """MEDIA-4: il DSL scrive le liste talvolta come dict singolo; esecuzione
    e gate devono vedere lo stesso albero, altrimenti il gate G2 e' cieco
    sui rami scritti in forma dict (runtime ok, classificazione falsata)."""
    if isinstance(node, dict):
        return [node]
    return node if isinstance(node, list) else []


def _declared(cmd: dict, name: str) -> list[str]:
    """Params del comando: lista dichiarata, altrimenti i placeholder
    ``<...>`` del nome (comandi con firma nel nome, es. /quiz_bestworst)."""
    p = cmd.get("params")
    if p:
        return p
    return [t.strip("<>") for t in str(name).split()[1:] if t.startswith("<")]


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

    env.filters.update(
        length=length, count=length, join=join, map=map_filter, sum=sum_filter
    )


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
    """Env native per value/if: QUALUNQUE nome non risolto degrada a None —
    typo inclusi (lo segnalano i gate G2/G3, non un crash a runtime).
    'assente' nello stato del DSL significa 'non ancora valorizzato'."""

    def __getattr__(self, name: str) -> None:
        return None

    def __getitem__(self, key: Any) -> None:
        return None

    def __str__(self) -> str:
        return ""


ESEGUIBILI = frozenset(
    {
        "set",
        "append",
        "extend",
        "clear",
        "copy",
        "increment",
        "update_dict",
        "if",
        "when",
        "foreach",
        "for",
        "switch",
        "set_mode",
        "output",
        "output_template",
        "call",
        "compute",
        "command",
        "call_command",
        "route",
        "parse_json",
        "find_in",
        "guard_all",
        "error",
        "abort",
        # ES2-a1 (ADR 009): archivio sessione — i verbi toccano solo la porta
        "save_session",
        "load_session",
        "list_session_keys",
        "emit_event",
        "replace_placeholder",
        # ES2-a3 (ADR 010): export — persiste l'ultimo output su porta
        "export",
        # ES2-b (ADR 012): goto_state — atterra + renderizza, validato
        "goto_state",
        # ES3-2 (ADR 014): chiusura wizard come action (`- end: true`)
        "end",
    }
)

# ES1: no-op dichiarati. ES2-a1 save/load/list/emit/replace_placeholder,
# ES2-a3 export, ES2-b goto_state resi eseguibili; ES3 (ADR 013) ha reso
# eseguibili gli 11 verbi dominio con helper omonimi (DOMAIN_VERBS).
# ES4 = routing (match/match_any/invoke).
# ES3 (ADR 013): verbi dominio = zucchero su helper omonimi gia' nei moduli
# (verificati nel `helpers:` dei rispettivi file). Un unico _v_domain_call
# li serve tutti: `as` e' escluso dai kwargs perche' keyword Python.
DOMAIN_VERBS = frozenset(
    {
        "compute_xp_budget_estimate",
        "classify_balance_label",
        "estimate_party_benchmarks",
        "estimate_enemy_benchmarks",
        "detect_risks",
        "compute_effective_cr_from_enemies",
        "build_risk_heatmap",
        "build_top_risks",
        "build_buylist",
        "find_and_consume_item",
        "find_and_update_item",
    }
)

# ES3 (ADR 013): verbi dichiarati senza helper omonimo — restano NO_OP con
# motivo "non_implementato" (mai competenza finta), log backlog.
_NO_HELPER_VERBS = frozenset(
    {
        "generate_enemies_from_biome",
        "analyze_meta_results",
        "search_meta_sources",
        "run_qagates",
        "cross_reference_class",
        "find_in_list",
    }
)

NO_OP = frozenset(
    {
        "roll",
        "match",
        "match_any",
        "invoke",
        "search_meta_sources",
        "find_in_list",
        "run_qagates",
        "cross_reference_class",
        # ES3 (ADR 013): dichiarati senza helper — motivo "non_implementato"
        "generate_enemies_from_biome",
        "analyze_meta_results",
    }
)

STRUCTURAL = frozenset(
    {
        "value",
        "with",
        "then",
        "else",
        "actions",
        "do",
        "cases",
        "when",
        "loop_as",
        "return_as",
        "as",
        "to",
        "from",
        "where",
        "equals",
        "input",
        "key",
        "append_values",
        "on_fail",
        "requires",
        "passthrough",
        "by",
        "logic",
    }
)

_BUILTINS = {}


def _builtins() -> dict[str, Any]:
    if not _BUILTINS:
        import builtins

        for name in (
            "str",
            "int",
            "float",
            "len",
            "any",
            "all",
            "sum",
            "max",
            "min",
            "sorted",
            "round",
            "list",
            "dict",
            "set",
            "tuple",
            "enumerate",
            "zip",
            "range",
            "reversed",
            "abs",
            "bool",
        ):
            _BUILTINS[name] = getattr(builtins, name)
    return _BUILTINS


class Interpreter:
    def __init__(
        self,
        kernel: Kernel,
        port: JsonFilePort | None = None,
        export_port: ExportDirPort | None = None,
    ):
        self.kernel = kernel
        # ADR 009: l'archivio sessione vive nell'interprete (mai in
        # load_kernel). Default lazy-safe: senza file esistente la porta e'
        # vuota e i moduli ES1 non la toccano.
        self.port = port if port is not None else JsonFilePort()
        self.state: dict[str, Any] = {
            root: {}
            for root in (
                "build_state",
                "local",
                "runtime",
                "benchmarks",
                "loot_state",
                "tavern_state",
                "encounter_state",
                "story_state",
                "doc_state",
                "qa_result",
            )
        }
        # ADR 010: porta export iniettata come la porta sessione (ADR 009)
        self.export_port = export_port if export_port is not None else ExportDirPort()
        # ADR 014: stato condiviso GameMode = deepcopy di GameMode.shared
        # (mai kernel.data: statico e condiviso tra interpreti). Target
        # `@GameMode.` risolti qui via Interpreter._tp.
        _gm_shared = (
            kernel.data.get("state_machine", {}).get("GameMode", {}).get("shared")
        )
        if isinstance(_gm_shared, dict):
            # Codex P1 #559: un livello `shared` — letture e scritture
            # usano entrambe game_mode.shared.* (@GameMode.shared -> _tp)
            self.state["game_mode"] = {"shared": _copy.deepcopy(_gm_shared)}
        self.scratch: dict[str, Any] = {}
        self.output_log: list[str] = []
        self.noop_log: list[dict[str, str]] = []
        self.events: list[dict[str, Any]] = []
        # ADR 008: nomi gia' risolvibili senza i params (stato, dati modulo,
        # helper, builtin, radici di stato): un ref a questi NON e' "non
        # legato" anche se omonimo di un param assente.
        self._known = (
            set(_builtins())
            | set(kernel.data)
            | {h.split(".")[0] for h in kernel.helpers}
            | set(self.state)
            | {"GameMode"}  # ADR 014: alias di stato game_mode, sempre nel ctx
        )
        self._saltati: list[str] = []  # target/arg saltati nel frame corrente
        self._unbound: set[str] = set()  # params dichiarati-non passati (frame)
        self._guards: dict[str, None] = {}  # None-fill SOLO per le condizioni
        # ALTA-1 (review Claude): senza __builtins__ esplicito, Python
        # inietta i builtin veri e la whitelist import e' teatro (eval/open
        # esisterebbero lo stesso). MODELLO DI MINACCIA: protezione contro
        # refusi/errore accidentale, NON isolamento — in-process non si
        # chiude (ogni funzione espone __globals__; random importa os).
        # Prerequisito duro: i moduli vengono SOLO dal repo. Se un modulo
        # arrivera' mai da utente/modello (homebrew), isolamento a livello
        # di processo: e' una precondizione ES2/ES3, non un fix locale.
        safe_builtins = {
            k: v for k, v in vars(builtins).items() if k not in DENIED_BUILTINS
        }
        safe_builtins["__import__"] = _safe_import  # import statement -> whitelist
        self._g: dict[str, Any] = {"__builtins__": safe_builtins, **_builtins()}
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
        ctx.update(clean(self.kernel.data))  # MEDIA-6: i dati del modulo
        for root in self.state.values():  # cedono alle chiavi di stato
            if isinstance(root, dict):
                ctx.update(clean(root))
        ctx.update(self.state)
        ctx.update(clean(self.scratch))
        # Codex P2 (giro 4, review #553): nei render NATIVI i params
        # dichiarati-omessi mascherano le omonime chiavi di stato (None):
        # '{{ n or 3 }}' con n omesso prende il fallback, non build_state.n.
        # Negli output restano assenti (nessuna stampa fantasma di "None").
        # Gli skip restano statici e precedenti al render: qui non salvano.
        if not output:
            ctx.update(self._guards)
        # ADR 014: alias GameMode per i template dei nodi wizard
        # (@GameMode. normalizzato a GameMode. prima del render)
        ctx["GameMode"] = self.state.get("game_mode") or {}
        ctx.update(clean(params))
        ctx.update(self.kernel.helper_funcs(self._g))
        return ctx

    def _rn(self, value: Any, params: dict) -> Any:
        """Render native (value/if/when): bool e int nativi; chiave mancante
        su dict esistente -> None (assente = non valorizzato). Mapping e
        liste sono resi ricorsivamente (Codex P1: senza, `set: value:
        {nome: '{{nome}}'}` persisteva il template letterale nello stato,
        vedi minmax_builder /save_character)."""
        if isinstance(value, dict):
            return {k: self._rn(v, params) for k, v in value.items()}
        if isinstance(value, list):
            return [self._rn(v, params) for v in value]
        if not isinstance(value, str) or ("{{" not in value and "{%" not in value):
            return value
        if "@" in value:  # ADR 014: @GameMode. -> GameMode. (alias in ctx)
            value = value.replace("@GameMode.", "GameMode.")
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
        if "@" in value:  # ADR 014: alias @GameMode.
            value = value.replace("@GameMode.", "GameMode.")
        return self._std.from_string(value).render(self._ctx(params, output=True))

    def _resolve(self, ref: Any, params: dict) -> Any:
        """Risolve un riferimento: template, poi scratch, poi path nello
        stato, poi dati modulo (ordine = precedenza del DSL)."""
        value = self._rn(ref, params)
        if isinstance(value, str):
            head, _, rest = value.partition(".")
            if head in self.scratch:  # ALTA-3: lo scratch prima dello stato
                return _attr(self.scratch[head], rest) if rest else self.scratch[head]
            found = get_path(self.state, value, None)
            if found is not None:
                return found
            return get_path(self.kernel.data, value, None)
        return value

    # -- esecuzione comandi ----------------------------------------------

    def _state_keys(self) -> set:
        """Chiavi flatten dello stato attualmente valorizzate (ctx.update di
        _ctx espone ogni root come nomi liberi). Codex P2-1: un ref a una
        chiave valorizzata risolve davvero — non e' un wipe. Solo valori non
        None: una chiave None rende None = wipe, va saltato."""
        out: set = set()
        for root in self.state.values():
            if isinstance(root, dict):
                out |= {k for k, v in root.items() if v is not None}
        return out

    def _unresolvable(self, node: Any, params: dict) -> set:
        """ADR 008: nomi referenziati dal nodo che il contesto corrente NON
        puo' risolvere. Due famiglie: (1) param DICHIARATO-non passato —
        fonte primaria mancante, salta anche se esiste un'omonima chiave di
        stato (il param ha precedenza concettuale, l'evento deve dire il
        vero); (2) nome libero non dichiarato e non in known/scratch/stato/
        params (contaminazione scratch, refusi). Un verbo mutante su questi
        nomi e' no-op: scriverebbe un valore falso (None reso).

        set(self.state) oltre a _known/_state_keys: le radici create
        DINAMICAMENTE dai comandi (forked_build di /fork_build, forked di
        /fork_encounter) vivono in self.state e _ctx le espone a render —
        lo skip statico deve riconoscere cio' che il render risolve davvero
        (review Codex P2 #554 giro 6)."""
        refs = _referenced_vars(node)
        liberi = refs - self._unbound
        return (refs & self._unbound) | (
            liberi
            - self._known
            - set(self.state)
            - self._state_keys()
            - set(self.scratch)
            - set(params)
        )

    def _guard_ctx(self, params: dict) -> dict:
        """ADR 008: le CONDIZIONI mantengono la semantica pre-ES1 — un param
        dichiarato-non passato e' None per if/when/switch (guardia intatta).
        I verbi mutanti invece vedono params senza None-fill: li' "assente"
        non scrive affatto."""
        return {**self._guards, **params} if self._guards else params

    def _skip_node(self, node: Any, target: str, params: dict) -> bool:
        """True se l'action va saltata (target registrato tra i saltati)."""
        if self._unresolvable(node, params):
            self._saltati.append(target)
            return True
        return False

    # ---- Wizard input routing (ADR 014) --------------------------------

    _MATCH_NO_ACTION = object()  # parse match senza entry-action (regex)

    def run_input(self, text: str, _depth: int = 0) -> None:
        """Input libero utente: se runtime.current_state punta a un nodo
        wizard, match parse -> entry action -> guards -> node actions ->
        next/end -> prompt. Il DSL resta sincrono: il game loop e'
        dell'host (chi chiama run_input). Mai silenzioso."""
        cur = get_path(self.state, "runtime.current_state")
        if not isinstance(cur, str) or not cur or "." not in cur:
            self.events.append({"input_fuori_wizard": str(text)[:80]})
            return
        head = cur.split(".", 1)[0]
        sm = self.kernel.data.get("state_machine") or {}
        node = get_path(sm, cur)  # i path wizard sono relativi a state_machine
        if head != "GameMode" or not isinstance(node, dict):
            self.events.append({"nodo_wizard_mancante": cur})
            return
        if text.startswith("/"):
            head = text.split()[0]
            known = head in self.kernel.commands or any(
                n.split(" ", 1)[0] == head for n in self.kernel.commands
            )
            if known:
                # Codex P2 #559 giro 3: l'input intero va al dispatcher —
                # gli argomenti dopo il nome arrivano al comando (spec
                # parser quote-aware), non si scarta tutto dopo il nome.
                # Codex P1 #559 giro 7: render=False — l'input utente NON
                # e' un template del repo: mai _rn (Jinja non sandboxed),
                # gli argomenti restano letterali.
                self._dispatch_command(text, _depth, {"input": text}, render=False)
                return
            # comando sconosciuto: il nodo lo consuma come testo (ES4
            # aggiungera' il router davanti)
        params: dict[str, Any] = {"input": text}
        entry = self._match_parse(node.get("parse") or {}, text, params)
        if entry is None:
            self.events.append({"parse_non_riconosciuto": str(text)[:80], "nodo": cur})
            return
        if entry is not self._MATCH_NO_ACTION:
            actions = entry if isinstance(entry, list) else [entry]
            self._run_actions(actions, params, _depth)
        for g in node.get("guards") or []:
            if isinstance(g, dict) and not self._cond(g.get("condition"), params):
                self.output_log.append(str(g.get("on_fail") or "guard fallita"))
                return  # si resta sul nodo, nessuna azione/avanzamento
        self._run_actions(node.get("actions") or [], params, _depth)
        # Codex P2 #559: un'action (end/command/goto) puo' aver spostato
        # lo stato: onorata, il next del nodo NON la sovrascrive
        if get_path(self.state, "runtime.current_state") != cur:
            return
        nxt = node.get("next")
        if node.get("end") or nxt in (None, ""):
            set_path(self.state, "runtime.current_state", "IDLE")
            return
        self._advance(sm, cur, node, params, _depth + 1)

    def _advance(self, sm: dict, cur: str, node: dict, params: dict, depth: int) -> None:
        """Transizione di arrivo sul next del nodo. Prompt -> si ferma;
        end -> actions all'arrivo poi IDLE; action-only (Codex P1 #559
        giro 2) -> actions subito e avanzamento ricorsivo col suo next."""
        if depth > 20:  # ponytail: guard profondita' contro cicli action-only
            self.events.append({"avanzamento_profondita_max": cur})
            return
        nxt = node.get("next")
        if nxt in (None, ""):
            set_path(self.state, "runtime.current_state", "IDLE")
            return
        target = str(nxt)
        if target.startswith("@"):
            target = target[1:]
        else:  # fratello: stesso tema, altro nodo
            target = ".".join(cur.split(".")[:-1] + [target])
        nnode = get_path(sm, target)
        if not isinstance(nnode, dict):
            self.events.append({"nodo_wizard_mancante": target})
            return
        if nnode.get("when") is not None and not self._cond(nnode.get("when"), params):
            self.events.append({"wizard_guard_falso": target})
            return  # si resta sul nodo corrente
        # Codex P2 #559 giro 8: guard anche sul TEMA genitore — nei moduli
        # reali (KingdomTurn, MassCombat) il when vive sul tema, non sul
        # nodo entry; senza questo check il tema guardato esegue lo stesso
        theme = get_path(sm, ".".join(target.split(".")[:-1]))
        if (
            isinstance(theme, dict)
            and theme.get("when") is not None
            and not self._cond(theme["when"], params)
        ):
            self.events.append({"wizard_guard_falso": target})
            return
        set_path(self.state, "runtime.current_state", target)
        if nnode.get("prompt"):
            self.output_log.append(self._rs(str(nnode["prompt"]), params))
            return
        if nnode.get("end"):
            # nodo terminale: le actions girano all'arrivo, poi IDLE
            self._run_actions(nnode.get("actions") or [], params, depth)
            set_path(self.state, "runtime.current_state", "IDLE")
            return
        # nodo action-only: le actions girano all'arrivo, poi il suo next
        self._run_actions(nnode.get("actions") or [], params, depth)
        if get_path(self.state, "runtime.current_state") != target:
            return  # action end/goto/command ha gia' spostato lo stato
        self._advance(sm, target, nnode, params, depth + 1)

    def _match_parse(self, parse: dict, text: str, params: dict) -> Any:
        """Gerarchia ADR 014: map esatta > regex (ordine) > any/any_list.
        Groups regex legati in params. None = nessun match."""
        reserved = ("regex", "groups", "any", "any_list", "yes_no")
        for key, action in parse.items():
            if key in reserved:
                continue
            if str(key) == text:
                # Codex P2 #559 giro 4: entry guardata — when falsa/non
                # parsabile = non accettata, il match continua (catch-all)
                if isinstance(action, dict) and "when" in action:
                    w = self._cond(action["when"], params)
                    if not w:
                        continue
                    # giro 6: la guardia e' metadata — tolta prima del
                    # dispatch, sennò _dispatch invocherebbe _v_when sul
                    # sibling set e l'ordine chiavi YAML deciderebbe tutto
                    action = {k: v for k, v in action.items() if k != "when"}
                return action
        regex = parse.get("regex")
        patterns = regex if isinstance(regex, list) else [regex] if regex else []
        names = parse.get("groups") or []
        for pattern in patterns:
            m = re.match(str(pattern), text)
            if m:
                for i, gname in enumerate(names):
                    if i + 1 <= (m.lastindex or 0):
                        params[str(gname)] = m.group(i + 1)
                return self._MATCH_NO_ACTION
        if isinstance(parse.get("any_list"), dict):
            spec = parse["any_list"]
            sep = str(spec.get("sep") or ",")
            params[str(spec.get("as") or "items")] = [
                s.strip() for s in text.split(sep)
            ]
            return self._MATCH_NO_ACTION
        yn = parse.get("yes_no")
        if isinstance(yn, dict):
            # Codex P1 #559: nodo portrait — sì/no legato come boolean
            # al param dichiarato (key), consumato dalle actions via if
            key = str(yn.get("key") or "yes_no")
            t = text.strip().lower()
            if t in ("sì", "si", "sí", "yes", "y", "true", "1"):
                params[key] = True
                return self._MATCH_NO_ACTION
            if t in ("no", "n", "false", "0"):
                params[key] = False
                return self._MATCH_NO_ACTION
            return None
        if parse.get("any") is not None:
            action = parse["any"]
            # stessa guardia delle entry map: any con when falsa non consuma
            if isinstance(action, dict) and "when" in action:
                if not self._cond(action["when"], params):
                    return None
                return {k: v for k, v in action.items() if k != "when"}
            return action
        return None

    def _v_end(self, a, params, depth):
        # `- end: true` come action: chiude il wizard (node property end:
        # gestita da run_input)
        set_path(self.state, "runtime.current_state", "IDLE")

    def run_command(self, name: str, _depth: int = 0, **params: Any) -> None:
        cmd = self.kernel.commands.get(name)
        if cmd is None:
            raise DslAbort(f"comando sconosciuto: {name}")
        declared = _declared(cmd, name)
        # D8/ADR 008: assente in params != None passato. Solo i params
        # passati sono legati; gli altri sono "param non legato".
        bound = {p: params[p] for p in declared if p in params}
        unbound = sorted(p for p in declared if p not in params)
        prev_saltati, prev_unbound, prev_guards = (
            self._saltati,
            self._unbound,
            self._guards,
        )
        self._saltati = []
        self._unbound = set(unbound)
        self._guards = {p: None for p in unbound}
        snap = dict(self.scratch)
        saltati: list[str] = []
        try:
            self._run_actions(cmd.get("action") or [], bound, _depth)
            saltati = self._saltati
        finally:  # MEDIA-8: lo scratch di un comando non tracima al chiamante
            self.scratch.clear()
            self.scratch.update(snap)
            self._saltati, self._unbound, self._guards = (
                prev_saltati,
                prev_unbound,
                prev_guards,
            )
        self._sync()
        if saltati:  # evento aggregato: il merge parziale e' mai silenzioso
            self.events.append(
                {
                    "update_parziale": {
                        "comando": name,
                        "param_non_legati": unbound,
                        "saltati": saltati,
                    }
                }
            )

    def _run_actions(self, actions: list, params: dict, depth: int) -> None:
        for action in _as_list(actions):
            if not isinstance(action, dict):
                continue
            self._dispatch(action, params, depth)

    def _dispatch(self, a: dict, params: dict, depth: int) -> None:
        verb = next(
            (k for k in a if k in ESEGUIBILI or k in NO_OP or k in DOMAIN_VERBS),
            None,
        )
        if verb is None:
            self.noop_log.append({"verb": "?", "raw": str(a)[:120]})
            return
        if verb in DOMAIN_VERBS:
            self._v_domain_call(verb, a, params)
            return
        if verb in NO_OP:
            reason = "non_implementato" if verb in _NO_HELPER_VERBS else "declared"
            self.noop_log.append({"verb": verb, "reason": reason})
            return
        getattr(self, f"_v_{verb}")(a, params, depth)

    def _v_set(self, a, params, depth):
        target = a["set"]
        if isinstance(target, list):  # flow style: [{path: val}, ...]
            for item in target:
                for path, value in item.items():
                    if self._skip_node(value, str(path), params):
                        continue
                    self._set_target(path, self._rn(value, params))
            return
        if self._skip_node(a.get("value"), str(target), params):
            return
        self._set_target(target, self._rn(a.get("value"), params))

    @staticmethod
    def _tp(path: Any) -> Any:
        """ADR 014: target `@GameMode.` -> root di stato `game_mode.`
        (GameMode.shared vive in stato, mai in kernel.data statico)."""
        if isinstance(path, str) and path.startswith("@GameMode."):
            return "game_mode." + path[len("@GameMode.") :]
        return path

    def _set_target(self, path: str, value: Any) -> None:
        # set su variabile di loop: "e.stato" muta l'item puntato, non lo stato
        path = self._tp(path)
        head, _, rest = path.partition(".")
        if rest and isinstance(self.scratch.get(head), dict):
            set_path(self.scratch[head], rest, value)
            return
        set_path(self.state, path, value)

    def _v_append(self, a, params, depth):
        path = self._tp(a["append"])
        if self._skip_node(a.get("value"), str(path), params):
            return
        cur = get_path(self.state, path)
        if not isinstance(cur, list):
            cur = []
            set_path(self.state, path, cur)
        cur.append(self._rn(a.get("value"), params))

    def _v_extend(self, a, params, depth):
        path = self._tp(a["extend"])
        if self._skip_node(a.get("value"), str(path), params):
            return
        cur = get_path(self.state, path)
        if not isinstance(cur, list):
            cur = []
            set_path(self.state, path, cur)
        value = self._rn(a.get("value"), params)
        cur.extend(value if isinstance(value, list) else [value])

    def _v_clear(self, a, params, depth):
        set_path(self.state, self._tp(a["clear"]), [])

    def _v_copy(self, a, params, depth):
        set_path(
            self.state,
            self._tp(a["to"]),
            _copy.deepcopy(get_path(self.state, self._tp(a["copy"]))),
        )

    def _v_increment(self, a, params, depth):
        path = self._tp(a["increment"])
        set_path(
            self.state, path, (get_path(self.state, path) or 0) + int(a.get("by") or 1)
        )

    def _v_update_dict(self, a, params, depth):
        path = self._tp(a["update_dict"])
        if self._skip_node(a.get("key"), str(path), params) or self._skip_node(
            a.get("append_values"), str(path), params
        ):
            return
        cur = get_path(self.state, path)
        if not isinstance(cur, dict):
            cur = {}
            set_path(self.state, path, cur)
        key = self._rn(a.get("key"), params)
        values = self._rn(a.get("append_values"), params)
        cur.setdefault(key, []).extend(values if isinstance(values, list) else [values])

    def _v_if(self, a, params, depth):
        branch = (
            a.get("then")
            if self._cond(a["if"], self._guard_ctx(params))
            else a.get("else")
        )
        self._run_actions(branch or [], params, depth)

    def _v_when(self, a, params, depth):
        if self._cond(a["when"], self._guard_ctx(params)):
            self._run_actions(a.get("do") or [], params, depth)

    def _v_foreach(self, a, params, depth):
        ref = a["foreach"]
        # Codex P2 #559 giro 2: i binding del parse (any_list ecc.) vivono
        # in params — un nome nudo li trova prima di scratch/stato/kernel
        items = params.get(ref) if str(ref) in params else self._resolve(ref, params)
        if self._unresolved_foreach(ref, items):
            return
        self._loop(
            items or [],
            a.get("loop_as") or "item",
            a.get("actions") or [],
            params,
            depth,
        )

    def _v_for(self, a, params, depth):
        # forma: for: e in "{{ expr }}"  (+ do:)
        spec = str(a["for"])
        var, _, expr = spec.partition(" in ")
        var = var.strip()
        ref = expr.strip()
        items = params.get(ref) if ref in params else self._resolve(ref, params)
        if self._unresolved_foreach(ref, items):
            return
        self._loop(items or [], var, a.get("do") or [], params, depth)

    def _unresolved_foreach(self, ref: Any, items: Any) -> bool:
        """ALTA-3: nome non risolto (stringa o None da nome nudo) = evento,
        mai iterazione di caratteri e mai skip silenzioso. Un template che
        rende None e' invece una collezione vuota legittima."""
        if not isinstance(ref, str) or "{{" in ref or "{%" in ref:
            return False
        if isinstance(items, str) or items is None:
            self.events.append({"foreach_non_risolto": ref[:80]})
            return True
        return False

    def _loop(
        self, items: Any, var: str, actions: list, params: dict, depth: int
    ) -> None:
        saved = self.scratch.get(var, _MISSING)
        try:
            for item in items:
                self.scratch[var] = item
                self._run_actions(actions, params, depth)
        finally:  # ALTA-3: la var di loop non sopravvive al ciclo
            if saved is _MISSING:
                self.scratch.pop(var, None)
            else:
                self.scratch[var] = saved

    def _v_set_mode(self, a, params, depth):
        set_path(self.state, "runtime.mode", self._rn(a["set_mode"], params))

    def _v_goto_state(self, a, params, depth):
        # ADR 012: atterra + renderizza. Validazione a due vie, rifiuto a
        # evento mai silenzioso. La tabella transitions e' metadato
        # dichiarativo per il planner, NON enforced (goto imperativo e
        # tabella dichiarativa sono ortogonali; ~30% dei goto reali non
        # hanno transizione dichiarata).
        target = self._rn(a.get("goto_state"), params)
        sm = self.kernel.data.get("state_machine") or {}
        motivo = ""
        if not isinstance(target, str) or not target:
            motivo = "target vuoto/non stringa"
        elif "." not in target:
            if target not in (sm.get("states") or []):
                motivo = "non in state_machine.states"
        else:
            segs = target.split(".")
            sub = sm.get(segs[0])
            # container (GameMode) e tema (es. Gambling) dichiarati; il nodo
            # foglia no (YAGNI: niente registro statico dei ~20 nodi)
            if not isinstance(sub, dict) or segs[1] not in sub:
                motivo = "percorso wizard non dichiarato"
        if motivo:
            self.events.append({"stato_non_valido": str(target)[:80], "motivo": motivo})
            return
        set_path(self.state, "runtime.current_state", target)
        node = get_path(sm, target)  # flat -> None; dotted -> nodo wizard
        if isinstance(node, dict) and node.get("prompt"):
            self.output_log.append(self._rs(node["prompt"], params))
        elif isinstance(node, dict):
            # Codex P2 #559 giro 7: atterraggio action-only via comando
            # (/chase_start, /gamble) — le actions girano all'arrivo e si
            # avanza (stesso _advance dei nodi end/action-only)
            self._run_actions(node.get("actions") or [], params, depth)
            if get_path(self.state, "runtime.current_state") == target:
                self._advance(sm, target, node, params, depth + 1)

    def _v_switch(self, a, params, depth):
        guards = self._guard_ctx(params)
        value = self._rn(a["switch"], guards)
        for case in a.get("cases") or []:
            if isinstance(case, dict) and str(
                self._rn(case.get("when"), guards)
            ) == str(value):
                self._run_actions(case.get("do") or [], params, depth)
                return

    def _v_output(self, a, params, depth):
        self.output_log.append(self._rs(a.get("output"), params))

    def _v_output_template(self, a, params, depth):
        name = a["output_template"]
        if "{{" in name or "{%" in name:  # template inline, non un nome
            self.output_log.append(
                self._std.from_string(name).render(self._ctx(params, output=True))
            )
            return
        tmpl = self.kernel.templates.get(name)
        if tmpl is None:
            raise DslAbort(f"template mancante: {name}")
        self.output_log.append(
            self._std.from_string(tmpl).render(self._ctx(params, output=True))
        )

    def _v_call(self, a, params, depth):
        name = a["call"]
        if self._skip_node(a.get("with"), f"call:{name}", params):
            # ADR 008 + Codex P2 (review #553 giro 2): un risultato gia' in
            # scratch e' STALE — mascherarlo renderebbe i set dipendenti
            # scrivibili col valore vecchio. Va tolto: senza scratch[as]
            # il resto del comando vede il nome non legato (contaminazione
            # naturale)
            if a.get("return_as"):
                self.scratch.pop(a["return_as"], None)
            return
        fn = self._g.get(name) or self._g.get(
            re.sub(r"\W", "_", name)
        )  # helper dotted: il def compilato usa nome python safe (Codex P3)
        if not callable(fn):
            self.noop_log.append(
                {"verb": f"call:{name}", "motivo": "helper non compilato"}
            )
            return
        kwargs = {k: self._rn(v, params) for k, v in (a.get("with") or {}).items()}
        result = fn(**kwargs)
        if a.get("return_as"):
            self.scratch[a["return_as"]] = result

    def _v_domain_call(self, verb: str, a: dict, params: dict) -> None:
        # ADR 013: il verbo dominio e' zucchero su `call <helper omonimo>` —
        # i params del verbo sono i kwargs dell'helper, `as` e' il nome
        # scratch del risultato (escluso dai kwargs: keyword Python).
        # Convenzioni identiche a _v_call: _skip_node ADR 008, helper non
        # compilato rendicontato, scratch stale rimosso.
        spec = a.get(verb) or {}
        as_name = spec.get("as")
        # ADR 008: _skip_node solo sui kwargs (come `with` in _v_call) —
        # `as` e' il nome di SCRITTURA del risultato, non un param letto
        if self._skip_node(
            {k: v for k, v in spec.items() if k != "as"},
            f"domain:{verb}",
            params,
        ):
            if as_name:
                self.scratch.pop(as_name, None)
            return
        fn = self._g.get(verb)  # nomi dominio sono identificatori safe
        if not callable(fn):
            self.noop_log.append({"verb": verb, "motivo": "helper non compilato"})
            return
        kwargs = {
            k: self._resolve_ref(self._rn(v, params))
            for k, v in spec.items()
            if k != "as"
        }
        result = fn(**kwargs)
        if as_name:
            self.scratch[as_name] = result

    def _resolve_ref(self, value: Any) -> Any:
        """Codex P2 (#558): stringa bare che e' un path di stato risolta
        all'oggetto vivo — helper come find_and_update_item mutano la lista
        (in_list: loot_state.inventory); passare la stringa e' un TypeError
        /AttributeError al call-time. Stringhe non path restano stringhe."""
        if isinstance(value, str) and "{{" not in value and "." in value:
            obj = get_path(self.state, value, _MISSING)
            if obj is not _MISSING:
                return obj
        return value

    def _v_compute(self, a, params, depth):
        body = (a.get("logic") or "").rstrip()
        if "{{" in body and "\n" not in body:
            # Codex P4: forma espressione (ruling_expert, narrative_flow) —
            # template su riga unica, non corpo Python: render nativo nel
            # contesto del comando, poi coercizione letterale/aritmetica.
            if self._skip_node(body, str(a["compute"]), params):
                return
            value = self._rn(body, params)
            if isinstance(value, str):
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    try:
                        value = eval(value, {"__builtins__": {}}, self._ctx(params))
                    except Exception:
                        pass  # ponytail: resta la stringa renderizzata
            set_path(self.state, a["compute"], value)
            return
        src = "def __compute():\n" + textwrap.indent(body, "    ")
        exec(compile(src, "<compute>", "exec"), self._g)
        set_path(self.state, a["compute"], self._g["__compute"]())

    def _v_command(self, a, params, depth):
        extra: dict = {}
        ap = a.get("params")
        if isinstance(ap, dict) and ap:
            # Codex P2 #559 giro 2 (end-to-end): i params dichiarati
            # sull'action erano ignorati — il comando girava senza kwargs
            # ("Oggetto aggiunto: ."). Resi nel contesto del chiamante
            # (scratch di loop incluso), vincolati da run_command ai
            # params dichiarati del comando.
            # Codex P2 #559 giro 4: una chiave che referenzia un param del
            # chiamante omesso si OMETTE prima del render — sennò '{{x}}'
            # reso None diventerebbe "legato" e aggirerebbe la protezione
            # unbound (wipe silenzioso, come i token stringa del dispatcher).
            ok = {}
            for k, v in ap.items():
                if self._unresolvable(v, params):
                    self._saltati.append(f"param:{k}")
                    continue
                ok[k] = v
            extra = self._rn(ok, params)
        spec = a.get("command") or a.get("route") or a.get("call_command")
        if extra:
            params = {**params, **extra}
        self._dispatch_command(spec, depth, params, extra or None)

    def _v_call_command(self, a, params, depth):
        self._dispatch_command(a.get("call_command") or a.get("command"), depth, params)

    def _v_route(self, a, params, depth):
        self._dispatch_command(a.get("route"), depth, params)

    def _dispatch_command(
        self,
        spec: Any,
        depth: int,
        params: dict,
        extra: dict | None = None,
        render: bool = True,
    ) -> None:
        if depth >= MAX_DEPTH:
            raise DslAbort(f"ricorsione command: oltre profondita {MAX_DEPTH}")
        if not isinstance(spec, str):
            raise DslAbort(f"command non stringa: {spec!r}")
        # ADR 008: i token che referenziano nomi non legati vengono scartati
        # PRIMA del render (sennò '/inner count=None' e il wipe e' silenzioso).
        # Codex P2 (review PR #553): il tokenizer e' quote-aware — gli argomenti
        # quoted sono UN token anche con spazi (mai quote spezzate) — e il drop
        # avviene prima del render (mai coercizioni di una sentinella da
        # filtri/aritmetica, mai TypeError). Gli slot posizionali dei token
        # scartati restano occupati: i sopravvissuti non slittano di parametro.
        kept: list[str] = []
        slots: list[int] = []  # slot posizionale di ogni kept posizionale
        pos = 0
        toks = _SPEC_TOKEN_RE.findall(spec)
        head = (
            toks[0] if toks else ""
        )  # nome comando: mai droppato, mai renderizzato da solo
        for tok in toks[1:]:
            slot = -1
            if not _is_named_arg(tok):
                slot = pos
                pos += 1
            if render and self._unresolvable(tok, params):
                self._saltati.append(f"arg:{tok[:80]}")
                continue
            kept.append(tok)
            if slot >= 0:
                slots.append(slot)
        rendered = (
            self._rn(" ".join([head, *kept]), params) if render else " ".join([head, *kept])
        )  # Codex P2: render prima di tokenizzare; giro 7: solo per i
        # comandi del repo — l'input utente arriva letterale (render=False)
        try:
            tokens = shlex.split(rendered)
        except ValueError as e:  # quoting malformato (input utente)
            self.events.append({"tokenizzazione_fallita": str(e)[:80]})
            return
        if not tokens:
            return
        name = tokens[0]
        if name not in self.kernel.commands:
            # BASSA-13: nomi comando con firma ("/quiz_bestworst <set_id>"):
            # il dizionario chiave per la stringa intera, il modello scrive
            # il primo token -> prova il match sul primo token
            name = next(
                (n for n in self.kernel.commands if n.split(" ", 1)[0] == tokens[0]),
                name,
            )
        cmd = self.kernel.commands.get(name) or {}
        declared = _declared(cmd, name)
        kv: dict[str, Any] = {}
        # Codex P2 (giro 4): slot posizionali sequenziali a partire dallo
        # slot del primo kept — un template non quotato puo' espandersi in
        # piu' argomenti shlex e occupa gli slot in sequenza
        slots_iter = iter(slots)
        next_slot: int | None = None
        for tok in tokens[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k] = v
            else:
                if next_slot is None:
                    next_slot = next(slots_iter, None)
                if next_slot is None:
                    self.events.append({"argomento_posizionale_scolto": tok[:60]})
                elif next_slot < len(declared):  # MEDIA-5: posizionale dichiarato
                    kv[declared[next_slot]] = tok
                    next_slot += 1
                else:
                    self.events.append({"argomento_posizionale_scolto": tok[:60]})
        self.run_command(
            name, _depth=depth + 1, **{**kv, **(extra or {})}
        )  # ALTA-2: depth si propaga; params action dichiarati > token stringa

    def _v_parse_json(self, a, params, depth):
        o = a["parse_json"]
        if self._skip_node(o.get("input"), f"parse_json:{o.get('as')}", params):
            self.scratch.pop(o.get("as"), None)  # Codex P2 giro 2: stale
            return
        self.scratch[o["as"]] = json.loads(self._rs(o["input"], params))

    def _v_find_in(self, a, params, depth):
        f = a["find_in"]
        if self._skip_node(f, f"find_in:{f.get('as')}", params):
            self.scratch.pop(f.get("as"), None)  # Codex P2 giro 2: stale
            return
        lst = self._resolve(f.get("from"), params) or []
        where = f.get("where") or {}
        equals = self._rn(where.get("equals"), params)
        found = next(
            (
                it
                for it in lst
                if isinstance(it, dict) and it.get(where.get("field")) == equals
            ),
            None,
        )
        self.scratch[f["as"]] = found

    def _v_guard_all(self, a, params, depth):
        g = a["guard_all"] or {}
        if not get_path(self.state, g.get("requires") or ""):
            self.events.append({"guard_fail": g.get("on_fail")})

    def _v_error(self, a, params, depth):
        raise DslAbort(self._rs(a.get("error"), params))

    def _v_abort(self, a, params, depth):
        raise DslAbort(self._rs(a.get("abort") or "abort", params))

    # -- ES2-a1: archivio sessione (ADR 009) ------------------------------

    def _session_key(self, spec: dict, params: dict, verb: str) -> str | None:
        """Render + whitelist della chiave, UN punto per i verbi sessione:
        None + evento se la chiave referenzia nomi non legati (param omesso:
        mai una 'build_None' fabbricata, review Codex P2 #554 giro 2) o non
        rispetta la whitelist (mai sanificazione)."""
        if self._skip_node(spec.get("key"), f"{verb}:key", params):
            return None
        key = self._rn(spec.get("key"), params)
        if not isinstance(key, str) or not SESSION_KEY_RE.match(key):
            self.events.append(
                {"chiave_sessione_non_valida": str(key)[:80], "verb": verb}
            )
            return None
        return key

    def _v_save_session(self, a, params, depth):
        s = a["save_session"]
        key = self._session_key(s, params, "save_session")
        if key is None:
            return
        if self._skip_node(s.get("value"), f"save_session:{key}", params):
            return
        value = self._rn(s.get("value"), params)
        try:
            # P1 (review Codex #554): snapshot indipendente — senza deepcopy
            # la porta trattiene il dict vivo dello stato e le modifiche
            # successive al build mutano l'entry gia' salvata
            self.port.save(key, _copy.deepcopy(value))
        except (TypeError, ValueError) as exc:
            # mai str() silenzioso: un valore non serializzabile e' un
            # evento e nessuna scrittura
            self.events.append(
                {"valore_non_serializzabile": key, "dettaglio": str(exc)[:120]}
            )

    def _v_load_session(self, a, params, depth):
        s = a["load_session"]
        key = self._session_key(s, params, "load_session")
        self.scratch[s["as"]] = self.port.load(key) if key is not None else None

    def _v_list_session_keys(self, a, params, depth):
        s = a["list_session_keys"]
        if self._skip_node(s.get("prefix"), "list_session_keys:prefix", params):
            self.scratch[s["as"]] = []  # mai una lista da prefisso fabbricato
            return
        prefix = self._rn(s.get("prefix"), params)
        self.scratch[s["as"]] = (
            self.port.list(prefix) if isinstance(prefix, str) else []
        )

    def _v_emit_event(self, a, params, depth):
        e = a["emit_event"]
        topic = self._rn(e.get("topic"), params)
        payload = self._rn(e.get("payload"), params)
        self.port.emit(str(topic), payload)

    def _v_replace_placeholder(self, a, params, depth):
        # forma reale (minmax_builder): il placeholder letterale nella
        # variabile di loop e' risolto prima della search — lo sostituiamo
        # in TUTTE le stringhe dello scratch (1 occorrenza nei moduli).
        # forma del verbo: replace_placeholder: <segnaposto>  + with: (sibling)
        r = a["replace_placeholder"]
        placeholder = str(
            r if not isinstance(r, dict) else r.get("replace_placeholder")
        )
        value = self._rn(a.get("with"), params)
        for k, v in self.scratch.items():
            if isinstance(v, str) and placeholder in v:
                self.scratch[k] = v.replace(placeholder, str(value))

    def _v_export(self, a, params, depth):
        # ES2-a3 (ADR 010): forma scalare - export: <fmt>. Persiste l'ULTIMO
        # output (il documento appena renderizzato) su porta export. Il
        # formato e' reso da template, quindi whitelist: mai un nome file
        # arbitrario da input utente. Il NOME export_<n>.<ext> lo assegna la
        # porta dal contenuto della directory (mai un contatore volatile in
        # stato: review Codex P1 #555 giro 1).
        if self._skip_node(a.get("export"), "export:formato", params):
            return
        fmt = self._rn(a.get("export"), params)
        ext = str(fmt).strip().lower() if fmt is not None else ""
        if ext not in EXPORT_EXTENSIONS:
            self.events.append({"formato_export_non_valido": str(fmt)[:40]})
            return
        if not self.output_log:
            self.events.append({"export_senza_output": ext})
            return
        name = self.export_port.write(ext, self.output_log[-1])
        self.scratch["exported_path"] = name

    # -- report di copertura (G2) ----------------------------------------

    def coverage_report(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "totale": 0,
            "eseguibile": 0,
            "no_op": 0,
            "no_op_cmds": [],
            "errore": [],
            # ADR 011: comandi sovrascritti in caricamento pieno (gate)
            "shadowed": sorted(self.kernel.shadowed),
        }
        for name, cmd in self.kernel.commands.items():
            report["totale"] += 1
            verbs: set[str] = set()
            self._collect_verbs(cmd.get("action") or [], verbs)
            unknown = verbs - ESEGUIBILI - NO_OP - DOMAIN_VERBS
            missing_tmpl = [
                t
                for t in self._templates_in(cmd.get("action") or [])
                if t not in self.kernel.templates
            ]
            if unknown or missing_tmpl:
                report["errore"].append(
                    {
                        "comando": name,
                        "verbi_sconosciuti": sorted(unknown),
                        "template_mancanti": missing_tmpl,
                        "origin": cmd.get("origin"),
                    }
                )
            elif verbs & NO_OP:
                report["no_op"] += 1
                report["no_op_cmds"].append(name)
            else:
                report["eseguibile"] += 1
        return report

    def _collect_verbs(self, actions: list, verbs: set) -> None:
        for action in _as_list(actions):
            if not isinstance(action, dict):
                continue
            for key in action:
                if key in ESEGUIBILI or key in NO_OP:
                    verbs.add(key)
                elif key not in STRUCTURAL:
                    verbs.add(
                        key
                    )  # candidato sconosciuto: la classificazione lo rivela
            for key in ("then", "else", "actions", "do"):
                self._collect_verbs(action.get(key), verbs)
            for case in _as_list(action.get("cases")):
                if isinstance(case, dict):
                    self._collect_verbs(case.get("do"), verbs)

    def _templates_in(self, actions: list) -> list[str]:
        found: list[str] = []
        for action in _as_list(actions):
            if isinstance(action, dict):
                name = action.get("output_template")
                if isinstance(name, str) and "{{" not in name and "{%" not in name:
                    found.append(name)
                for key in ("then", "else", "actions", "do"):
                    found.extend(self._templates_in(action.get(key)))
                for case in _as_list(action.get("cases")):  # BASSA-10
                    if isinstance(case, dict):
                        found.extend(self._templates_in(case.get("do")))
        return found
