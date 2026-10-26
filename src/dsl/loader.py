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

ALLOWED_IMPORTS = frozenset({"re", "random", "datetime", "math", "json"})

TEMPLATE_KEYS = ("ui_templates", "qa_templates", "export_templates")


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    if str(name).split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import non permesso dal DSL: {name!r}")
    return __import__(name, *args, **kwargs)


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
        return {n: g[h["py"]] for n, h in self.helpers.items()
                if "py" in h and callable(g.get(h["py"]))}

    def static_check(self) -> dict[str, list[str]]:
        """G3: compile di ogni logic + parse di ogni stringa template."""
        import jinja2

        logic_errori = list(self.helper_compile_errors)
        env = jinja2.Environment()
        template_errori: list[str] = []
        for fname, data in self.modules:
            for err in _walk_templates(data, env):
                template_errori.append(f"{fname}: {err}")
        return {"logic_errori": logic_errori, "template_errori": template_errori}


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


def load_kernel(modules_dir: Path, kernel_name: str = "base_profile.txt",
                only: tuple[str, ...] = ()) -> Kernel:
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
                    isinstance(val, dict) and "template" in key):
                continue
            k.data[key] = val
        for key in ("helpers", "functions"):
            for name, spec in (data.get(key) or {}).items():
                if isinstance(spec, dict) and "logic" in spec:
                    k.helpers[str(name)] = {
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
