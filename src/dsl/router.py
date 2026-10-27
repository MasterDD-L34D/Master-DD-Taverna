"""Router input libero (ADR 015, ES4): solo regex deterministico.

La tabella `router:` dei moduli (rules ordinate, fallback_policy,
decorators) viene valutata sull'input normalizzato. Le flag di pipeline
(embedding/rerank) e gli invoke sono NO_OP motivati in noop_log —
mai competenza finta (RZ1). Wizard e / restano a run_input (ADR 014):
l'host chiama route_input solo per input libero fuori wizard.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.dsl.state import get_path, set_path

MAX_SEGMENTS = 8  # ponytail: cap segmenter, contro split_regex esplosivi
_PIPELINE_NOOP = "pipeline_non_implementata"


class Router:
    def __init__(self, it: Any):
        self.it = it
        self.spec = it.kernel.data.get("router") or {}

    # -- pubblico --------------------------------------------------------

    def route(self, text: str) -> str | None:
        if not self.spec:
            self.it.events.append({"router_mancante": True})
            return None
        idt = self.spec.get("intent_detection") or {}
        set_path(self.it.state, "runtime.route_to", None)  # reset di turno
        self._decorators("pre_routing", {})
        candidates: list[str] = []
        set_path(self.it.state, "runtime.intent_candidates", [])  # reset di turno
        for seg in self._segments(text, idt.get("segmenter") or {}):
            self._route_segment(
                self._normalize(seg, idt.get("normalize") or {}), candidates
            )
        if not candidates:
            # fallback = default dell'INPUT intero (ADR 015): una rule con
            # `fallback:` vale solo a candidato zero, mai per segmento —
            # sennò il merge dipenderebbe dall'ordine dei segmenti
            for rule in self.spec.get("rules") or []:
                if isinstance(rule, dict) and rule.get("fallback"):
                    candidates.append(str(rule["fallback"]))
                    break
        policy = self.spec.get("fallback_policy") or {}
        set_path(self.it.state, "runtime.intent_candidates", candidates)
        if len(candidates) > 1:
            # disambiguazione authored a input intero (Codex P2 #560 g4):
            # le rule after_segments si valutano UNA volta sui candidati
            # finali — mai parziale dentro ogni segmento
            text_n = self._normalize(text, idt.get("normalize") or {})
            for rule in self.spec.get("rules") or []:
                if not isinstance(rule, dict) or not rule.get("after_segments"):
                    continue
                if not self._matches(rule, text_n):
                    continue
                self._apply_set(rule.get("set"), {"route_to": None})
                if rule.get("reply"):
                    self.it.output_log.append(self.it._rs(str(rule["reply"]), {}))
                return None
        if len(candidates) > 1:
            if policy.get("multi_match") == "ask_clarification":
                if policy.get("clarification_prompt"):
                    self.it.output_log.append(str(policy["clarification_prompt"]))
                return None
        winner = candidates[0] if len(candidates) == 1 else policy.get("no_match")
        if winner:
            set_path(self.it.state, "runtime.route_to", winner)
            self._decorators("post_routing", {"route_to": winner})
        return winner

    # -- segmenter / normalize -------------------------------------------

    def _regex_flags(self) -> int:
        return re.IGNORECASE if "i" in str(
            (self.spec.get("intent_detection") or {}).get("normalize", {}).get("regex_flags", "")
        ) else 0

    def _segments(self, text: str, seg: dict) -> list[str]:
        if not seg.get("enabled"):
            return [text]
        # Codex P2 #560 g3: lo split rispetta regex_flags configurate —
        # sennò "POI" maiuscolo non splitta e un short_circuit perde pezzi
        parts = [
            p
            for p in re.split(
                str(seg.get("split_regex") or "$^"), text, flags=self._regex_flags()
            )
            if p.strip()
        ]
        if len(parts) > MAX_SEGMENTS:
            self.it.events.append({"segmenter_troppi_segmenti": len(parts)})
            return [text]
        return parts or [text]

    @staticmethod
    def _normalize(text: str, norm: dict) -> str:
        out = text
        if norm.get("fold_accents"):
            out = "".join(
                c for c in unicodedata.normalize("NFD", out) if unicodedata.category(c) != "Mn"
            )
        if norm.get("lowercase"):
            out = out.lower()
        if norm.get("strip_punct"):
            out = re.sub(r"[^\w\s/]", " ", out)
        return out

    # -- rules ------------------------------------------------------------

    def _route_segment(self, text_n: str, candidates: list) -> list[str]:
        for rule in self.spec.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            if rule.get("fallback"):
                continue  # gestito a livello di route(): default a input
            if rule.get("after_segments"):
                continue  # valutata una sola volta a input intero in route()
            if not self._matches(rule, text_n):
                continue
            dest = rule.get("route_to")
            self._apply_set(rule.get("set"), {"route_to": None})
            for flag in ("embedding", "rerank", "eps_threshold"):
                if flag in rule:
                    self.it.noop_log.append({"verb": flag, "reason": _PIPELINE_NOOP})
            if dest and str(dest) not in candidates:
                candidates.append(str(dest))
                # Codex P2 #560: pubblicati PRIMA della rule successiva —
                # la disambiguazione authored li legge nel turno corrente,
                # non di quello prima
                set_path(
                    self.it.state, "runtime.intent_candidates", list(candidates)
                )
            if rule.get("reply"):
                self.it.output_log.append(self.it._rs(str(rule["reply"]), {}))
            if rule.get("stop") or rule.get("short_circuit"):
                break
            # continue / nessuna chiave: si prosegue la lista
        return candidates

    def _matches(self, rule: dict, text_n: str) -> bool:
        flags = self._regex_flags()
        pats = rule.get("match") or rule.get("match_any") or []
        pats = pats if isinstance(pats, list) else [pats]
        if pats and not any(re.search(str(p), text_n, flags) for p in pats):
            return False
        nots = rule.get("not_match") or []
        nots = nots if isinstance(nots, list) else [nots]
        if any(re.search(str(p), text_n, flags) for p in nots):
            return False
        cond = rule.get("condition")
        if cond is not None and not self._cond_router(cond, {}):
            return False
        return True

    def _cond_router(self, expr: Any, extra: dict) -> bool:
        """Condition authored della tabella: sintassi JS minimale tradotta
        (!x, &&, ||, .length) prima del parse — sennò ogni guard del
        router morirebbe come 'non parseggiabile' (vale falso + evento).
        Avvolta in {{ }} perche' _cond/_rn valutano SOLO template con
        delimitatori: una espressione bare resterebbe stringa non vuota =
        truthy TRUE sempre (Codex P1 #560)."""
        s = (
            str(expr)
            .replace("&&", " and ")
            .replace("||", " or ")
            .replace(".length", " | length")
        )
        s = re.sub(r"!(?!=)", " not ", s).strip()
        if not (s.startswith("{{") and s.endswith("}}")):
            s = "{{ " + s + " }}"
        return self.it._cond(s, extra)

    # -- decorators / set ---------------------------------------------------

    def _decorators(self, phase: str, extra: dict) -> None:
        blocks = ((self.spec.get("decorators") or {}).get(phase)) or []
        for blk in blocks:
            if not isinstance(blk, dict) or not self._cond_router(blk.get("if"), extra):
                continue
            for act in blk.get("then") or []:
                if not isinstance(act, dict):
                    continue
                if act.get("invoke"):
                    self.it.noop_log.append({"verb": "invoke", "reason": _PIPELINE_NOOP})
                elif "set" in act:
                    self._apply_set(act["set"], extra)

    def _apply_set(self, spec: Any, extra: dict) -> None:
        for item in spec if isinstance(spec, list) else [spec]:
            if not isinstance(item, dict):
                continue
            for path, value in item.items():
                set_path(self.it.state, str(path), self.it._rn(value, extra))
