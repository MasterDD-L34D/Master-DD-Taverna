#!/usr/bin/env python3
"""Layer flavor della forgia oggetti (cantiere item-gen A-leggera).

I numeri vengono da tools/item_forge (deterministico verificato); qui il
LLM (Ollama di default, provider iniettabile per i test) produce SOLO il
flavor: nome, descrizione evocativa (2-4 frasi, niente regole), max 3
bullet di dettaglio, nota playtest, hook narrativo. Output nel template
"Formato Torneo" ereditato dal legacy Item-generator.

Uso:
    python tools/item_forge_flavor.py "un anello che protegge dal fuoco" \
        --spell "resist energy" --cl 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config  # noqa: F401  (carica .env)
from tools.item_forge import forge_from_spell

FLAVOR_SYSTEM = """Sei un Game Master esperto di Pathfinder 1E. Scrivi SOLO il flavor di un oggetto magico, in italiano.

VINCOLI:
1. La descrizione e' SOLO evocativa (2-4 frasi): niente regole, numeri o meccaniche.
2. Dettagli: esattamente 3 bullet atomici su limitazioni/interazioni d'uso (qui le regole CI stanno).
3. Nota playtest: 1 riga onesta su rischi/abusi al tavolo.
4. Hook narrativo: 1 riga opzionale che aggancia l'oggetto a una storia.
5. Nome: evocativo ma sobrio, niente nomi propri di setting Paizo.

Rispondi SOLO con JSON valido:
{"name": "...", "description": "...", "details": ["...", "...", "..."],
 "playtest_note": "...", "narrative_hook": "..."}"""


def build_flavor_prompt(user_idea: str, forged: dict) -> str:
    """Prompt utente: idea + blocco deterministico come fatto vincolante."""
    return (
        f"Idea del GM: {user_idea}\n\n"
        f"DATI MECCANICI VINCOLANTI (gia' calcolati, non modificarli):\n"
        f"- incantesimo replicato: {forged['spell']} (livello {forged['spell_level']}, "
        f"LI {forged['caster_level']}), scuola: {forged['school_it']}\n"
        f"- prezzo: {forged['price']} mo, costo crafting: {forged['crafting_cost']} mo\n"
        f"- aura: {forged['aura']}, rarita': {forged['rarity']}\n"
        f"- tiro salvezza: {forged['saving_throw']}, RI: {forged['spell_resistance']}\n"
        f"- usi: {forged['uses']}"
    )


def _default_llm(messages: list[dict]) -> str:
    """LLM di default: Ollama OpenAI-compatible (env OLLAMA_BASE_URL /
    OLLAMA_MODEL, come il provider RAG di produzione)."""
    import httpx

    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
    resp = httpx.post(
        f"{base}/v1/chat/completions",
        json={"model": model, "messages": messages, "temperature": 0.7},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_flavor(raw: str) -> dict:
    """Estrae il JSON del flavor dalla risposta LLM (tollera testo attorno)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"risposta LLM senza JSON: {raw[:120]!r}")
    data = json.loads(raw[start : end + 1])
    for key in ("name", "description", "details", "playtest_note"):
        if key not in data:
            raise ValueError(f"flavor senza chiave {key!r}: {sorted(data)}")
    if not isinstance(data["details"], list) or len(data["details"]) != 3:
        raise ValueError("details deve essere una lista di 3 bullet")
    return data


def generate_flavor(user_idea: str, forged: dict, llm=None) -> dict:
    """Flavor via LLM (llm: callable(messages)->str, default Ollama)."""
    call = llm or _default_llm
    messages = [
        {"role": "system", "content": FLAVOR_SYSTEM},
        {"role": "user", "content": build_flavor_prompt(user_idea, forged)},
    ]
    return _parse_flavor(call(messages))


def render_tournament(forged: dict, flavor: dict) -> str:
    """Markdown Formato Torneo: numeri deterministici + flavor LLM."""
    lines = [
        f"# {flavor['name']}",
        "",
        f"**Aura** {forged['aura']} ({forged['school_it']}) · "
        f"**LI** {forged['caster_level']}° · **Slot** {forged.get('slot', '—')} · "
        f"**Prezzo** {forged['price']:,} mo · **Rarità** {forged['rarity']}",
        "",
        flavor["description"],
        "",
        f"**Attivazione**: {forged['uses']} · "
        f"**TS**: {forged['saving_throw']} · **RI**: {forged['spell_resistance']}",
        "",
        "**Dettagli**",
    ]
    lines += [f"- {d}" for d in flavor["details"]]
    lines += [
        "",
        f"**Costruzione**: {forged['crafting_cost']:,} mo "
        f"(requisito: incantesimo {forged['spell']})",
        "",
        f"**Nota playtest**: {flavor['playtest_note']}",
    ]
    if flavor.get("narrative_hook"):
        lines += ["", f"**Hook**: {flavor['narrative_hook']}"]
    lines += [
        "",
        "---",
        "_Numeri: deterministico verificato (item_forge) · "
        "Flavor: LLM (da verificare al tavolo)_",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("idea", help="idea dell'oggetto (lingua libera)")
    ap.add_argument(
        "--spell", required=True, help="incantesimo replicato (nome catalogo)"
    )
    ap.add_argument("--cl", type=int, required=True, help="livello incantatore")
    ap.add_argument("--uses", default="1/day", choices=["1/day", "3/day", "unlimited"])
    ap.add_argument(
        "--json", action="store_true", help="stampa il blocco JSON invece del markdown"
    )
    args = ap.parse_args(argv)

    forged = forge_from_spell(args.spell, args.cl, args.uses)
    flavor = generate_flavor(args.idea, forged)
    if args.json:
        print(
            json.dumps(
                {"forged": forged, "flavor": flavor}, ensure_ascii=False, indent=2
            )
        )
    else:
        print(render_tournament(forged, flavor))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
