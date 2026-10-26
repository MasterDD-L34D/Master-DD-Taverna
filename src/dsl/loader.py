"""Loader dei moduli YAML e materializzazione helper (exec controllato).

I moduli in src/modules/*.txt sono YAML valido. Questo modulo li parsa,
normalizza i due schemi di comandi (dizionario e lista), fonde kernel
(base_profile) e moduli (il modulo vince su chiavi omonime), e compila le
funzioni ``helpers:``/``functions:`` come corpi Python wrappati in def.

ponytail: l'exec gira su moduli fidati versionati dal repo — NON e' una
sandbox di sicurezza. Se i moduli arrivassero mai da terzi, passare a
no-op dichiarati.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

# ADR 008: value null/assente su questi verbi = wipe silenziale dello stato.
NULL_VALUE_VERBS = ("set", "append", "extend")

ALLOWED_IMPORTS = frozenset({"re", "random", "datetime", "math", "json", "hashlib"})

# builtins tolti ai helper: senza questi, open/eval/exec/globals non esistono
# nel namespace dei logic: (i moduli sono fidati, ma un riferimento errato
# a 'open' deve rompere forte, non aprire il file system)
DENIED_BUILTINS = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "globals",
        "locals",
        "vars",
    }
)

TEMPLATE_KEYS = ("ui_templates", "qa_templates", "export_templates")


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    if str(name).split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import non permesso dal DSL: {name!r}")
    return __import__(name, *args, **kwargs)


def _walk_helpers(prefix: str, node: Any) -> Iterator[tuple[str, dict]]:
    """Helper possono vivere sotto namespace (Taverna_NPC: Echo/GameMode/Quiz):
    discendi finche' non trovi una foglia con 'logic', con nome qualificato
    dotted (Codex P3: senza, i namespace interi venivano droppati)."""
    if isinstance(node, dict):
        if "logic" in node:
            yield prefix, node
        else:
            for sub, spec in node.items():
                yield from _walk_helpers(
                    f"{prefix}.{sub}" if prefix else str(sub), spec
                )


def _norm_commands(raw: Any) -> Iterator[tuple[str, dict]]:
    if isinstance(raw, dict):
        for name, spec in raw.items():
            if isinstance(spec, dict):
                yield str(name), spec
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("command")
                if name:
                    yield str(name), item


@dataclass
class Kernel:
    """Moduli caricati e fusi: comandi, helper, template e dati top-level."""

    modules: list[tuple[str, dict]] = field(default_factory=list)
    commands: dict[str, dict] = field(default_factory=dict)
    helpers: dict[str, dict] = field(default_factory=dict)
    templates: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    helper_compile_errors: list[str] = field(default_factory=list)

    def bind_globals(self, g: dict) -> None:
        """Compila ogni helper come ``def`` dentro il dict globals condiviso."""
        import re

        for name, h in self.helpers.items():
            # nomi helper possono essere dotted ("MinMax.apply"): il def
            # usa un nome python safe, la mappa originale->safe resta qui
            py = re.sub(r"\W", "_", name)
            h["py"] = py
            params = ", ".join(h.get("params") or [])
            body = (h["logic"] or "").rstrip()
            src = f"def {py}({params}):\n" + textwrap.indent(body, "    ")
            try:
                exec(compile(src, f"<helper:{name}>", "exec"), g)
            except Exception as exc:  # raccolto, mai silenzioso
                self.helper_compile_errors.append(f"{name}: {exc!r}")

    def helper_funcs(self, g: dict) -> dict[str, Any]:
        return {
            n: g[h["py"]]
            for n, h in self.helpers.items()
            if "py" in h and callable(g.get(h["py"]))
        }

    def static_check(self) -> dict[str, list[str]]:
        """G3: compile di ogni logic + parse di ogni stringa template."""
        import jinja2

        logic_errori = list(self.helper_compile_errors)
        env = jinja2.Environment()
        template_errori: list[str] = []
        for fname, data in self.modules:
            for err in _walk_templates(data, env):
                template_errori.append(f"{fname}: {err}")
        return {
            "logic_errori": logic_errori,
            "template_errori": template_errori,
            "null_errori": _value_null_violations(self.commands),
        }


def _walk_templates(node: Any, env: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(node, str):
        if "{{" in node or "{%" in node:
            try:
                env.parse(node)
            except Exception as exc:
                yield f"{prefix}: {exc!r}"
    elif isinstance(node, dict):
        for k, v in node.items():
            if k == "logic":  # corpo python: coperto dal compile, non Jinja
                continue
            yield from _walk_templates(v, env, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_templates(v, env, f"{prefix}[{i}]")


def _walk_actions(node: Any) -> Iterator[dict]:
    """Ogni action dict di un albero then/else/do/actions/cases (MEDIA-4:
    il DSL scrive le liste talvolta come dict singolo)."""
    for action in node if isinstance(node, list) else [node]:
        if not isinstance(action, dict):
            continue
        yield action
        for key in ("then", "else", "do", "actions"):
            yield from _walk_actions(action.get(key))
        for case in action.get("cases") or []:
            if isinstance(case, dict):
                yield from _walk_actions(case.get("do"))


def _value_null_violations(commands: dict[str, dict]) -> list[str]:
    """ADR 008 (divieto): value null/assente su verbo mutante = gate rosso.
    Le forme YAML null / ~ / chiave vuota parsano tutte a None."""
    out: list[str] = []
    for name, cmd in commands.items():
        for action in _walk_actions(cmd.get("action")):
            target = action.get("set")
            if isinstance(target, list):  # flow style: [{path: val}, ...]
                for item in target:
                    if isinstance(item, dict):
                        out += [
                            f"{name}: set {path}: value null"
                            for path, val in item.items()
                            if val is None
                        ]
                continue
            for verb in NULL_VALUE_VERBS:
                if action.get(verb) is not None and action.get("value") is None:
                    out.append(f"{name}: {verb} {action[verb]}: value null/assente")
            if action.get("update_dict") is not None:
                for key in ("key", "append_values"):
                    if key in action and action[key] is None:
                        out.append(
                            f"{name}: update_dict {action['update_dict']}: {key} null"
                        )
    return out


def load_kernel(
    modules_dir: Path, kernel_name: str = "base_profile.txt", only: tuple[str, ...] = ()
) -> Kernel:
    """Carica kernel + moduli. ``only`` limita i moduli extra (replay
    per-modulo: evita collisioni di nome comando tra moduli diversi)."""
    k = Kernel()
    files = sorted(Path(modules_dir).glob("*.txt"))
    kernel_files = [f for f in files if f.name == kernel_name]
    others = [f for f in files if f.name != kernel_name]
    if only:
        others = [f for f in others if f.name in only]
    for path in kernel_files + others:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        k.modules.append((path.name, data))
        for name, spec in _norm_commands(data.get("commands")):
            spec = dict(spec)
            spec["origin"] = path.name
            k.commands[name] = spec
        for key, val in data.items():  # dati top-level (meta_reference, ecc.)
            if key in ("commands", "helpers", "functions") or (
                isinstance(val, dict) and "template" in key
            ):
                continue
            k.data[key] = val
        for key in ("helpers", "functions"):
            for name, spec in _walk_helpers("", data.get(key) or {}):
                k.helpers[name] = {
                    "params": spec.get("params") or [],
                    "logic": spec["logic"] or "",
                    "origin": path.name,
                }
        for key, val in data.items():
            # chiavi template: quelle canoniche (nome nudo) + qualunque altra
            # dict *templates* (es. ui_templates_quiz_pro -> nome dotted)
            if not isinstance(val, dict) or "template" not in key:
                continue
            for name, tmpl in val.items():
                if isinstance(tmpl, str):
                    k.templates[f"{key}.{name}"] = tmpl
                    if key in TEMPLATE_KEYS:
                        k.templates.setdefault(str(name), tmpl)
    return k
