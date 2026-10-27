#!/usr/bin/env python3
"""Estrae da PCGen le ABILITA' DI CLASSE (tag CSKILL) -> pcgen-class-skills.json.

Perche' un file suo e non un campo in piu' su un output esistente: rigenerare
`pcgen-class-progression.json` o `pcgen-class-abilities.json` per aggiungere un
campo vuol dire riscriverli, e un file generato riscritto puo' PERDERE voci in
silenzio. Un file nuovo non puo' perdere niente.

Uso:
  python tools/import_pcgen_class_skills.py [--pcgen-repo PATH] [--out-dir PATH]
  python tools/import_pcgen_class_skills.py --report-only

--- DOVE STA IL DATO, e perche' non e' in un posto solo ---------------------

PCGen dichiara le abilita' di classe in TRE forme, e cercarne una sola fa
concludere che il dato non c'e' (misurato: succede davvero):

  1. `CSKILL:` sulla riga `CLASS:<nome>` dei file `*_classes.lst`
     -> classi di prestigio e classi PNG;
  2. un'abilita' con `KEY:<Classe> ~ Class Skills` (o `Class Skills ~ <Classe>`)
     nei file `*_abilities_class.lst` -> la maggior parte delle classi;
  3. un'abilita' `<Classe> Core Class Skills` -> le classi base del Manuale.

⚠️ LA TRAPPOLA DELLA FORMA 2: il NOME VISUALIZZATO di quelle abilita' e'
letteralmente "Class Skills". La classe sta nella `KEY:`. Chi raggruppa per nome
trova UNA voce chiamata "Class Skills" e conclude che il dato non c'e'.

⚠️ LA TRAPPOLA DI `iter_lst_records`: scarta le righe il cui primo campo
contiene ':' (serve a togliere SOURCE*/CAMPAIGN). Le righe `CLASS:<nome>`
cadono proprio li' dentro, quindi la forma 1 NON puo' usarla: ha un parser suo.

--- COSA QUESTO SCRIPT NON FA ------------------------------------------------

Non risolve i marcatori di FAMIGLIA (`TYPE=Craft`, `TYPE=Knowledge`,
`TYPE=Profession`): li esporta come stanno. Tradurli in abilita' singole e' una
decisione del consumatore, e prenderla qui la renderebbe invisibile a chi legge
il JSON.

Non verifica le liste contro il SRD. PCGen e' una TRASCRIZIONE, e su questo
progetto una trascrizione citata si e' gia' rivelata sbagliata 13 volte su 27
(U28). L'oracolo sta a valle, dove il dato viene adottato.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.import_pcgen_lst import (  # noqa: E402
    DATA_SUBDIR,
    DEFAULT_OUT_DIR,
    DEFAULT_PCGEN_REPO,
    LICENSE_TEXT,
    _pcgen_commit,
    iter_lst_records,
)
from tools.import_pcgen_classes import BOOK_CLASS_FILES  # noqa: E402

OUTPUT_FILE = "pcgen-class-skills.json"

# Le forme del nome, come compaiono in `KEY:` (forme 2 e 3).
KEY_SUFFIX = " ~ Class Skills"
KEY_PREFIX = "Class Skills ~ "
KEY_CORE_SUFFIX = " Core Class Skills"
# ⚠️ Forma BREVE, senza la parola "Class": e' quella dell'Unchained Rogue, la
# classe piu' usata fra quelle che restavano scoperte. E' un pattern piu' LARGO
# degli altri -- `~ Skills` puo' finire su un'abilita' che non c'entra -- ed e'
# per questo che una voce conta solo se porta anche un CSKILL. Il filtro sta
# gia' in `from_abilities_file`, che scarta prima di guardare la chiave.
KEY_SHORT_SUFFIX = " ~ Skills"


def _skills(value: str) -> list[str]:
    """`CSKILL:a|b|c` -> ["a", "b", "c"]. Ordine del file, deduplicato."""
    out: list[str] = []
    for part in value.split("|"):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def _class_from_key(key: str) -> str | None:
    """La classe dalla chiave dell'abilita', o None se non e' una delle tre forme."""
    if key.endswith(KEY_SUFFIX):
        return key[: -len(KEY_SUFFIX)].strip()
    if key.startswith(KEY_PREFIX):
        return key[len(KEY_PREFIX) :].strip()
    if key.endswith(KEY_CORE_SUFFIX):
        return key[: -len(KEY_CORE_SUFFIX)].strip()
    if key.endswith(KEY_SHORT_SUFFIX):
        return key[: -len(KEY_SHORT_SUFFIX)].strip()
    return None


def from_classes_file(text: str, book: str) -> list[dict]:
    """Forma 1: `CLASS:<nome>` con `CSKILL:` sulla stessa riga.

    Parser esplicito e non `iter_lst_records`, che scarta i primi campi con ':'.
    """
    out = []
    for raw in text.splitlines():
        if "CSKILL:" not in raw:
            continue
        fields = [f.strip() for f in raw.split("\t")]
        if not fields or not fields[0].startswith("CLASS:"):
            continue
        name = fields[0][len("CLASS:") :].strip()
        for field in fields[1:]:
            if field.startswith("CSKILL:"):
                out.append(
                    {
                        "class": name,
                        "skills": _skills(field[len("CSKILL:") :]),
                        "source_book": book,
                        "shape": "class-line",
                    }
                )
                break
    return out


def from_abilities_file(text: str, book: str) -> list[dict]:
    """Forme 2 e 3: l'abilita' interna che concede le abilita' di classe.

    ⚠️ Si guarda `KEY:`, MAI il nome: il nome visualizzato e' "Class Skills"
    per tutte, e raggrupparlo darebbe una voce sola per l'intero gioco.
    """
    out = []
    for name, tags in iter_lst_records(text):
        key, cskill = None, None
        for tag, value in tags:
            if tag == "KEY":
                key = value
            elif tag == "CSKILL":
                cskill = value
        if cskill is None:
            continue
        cls = _class_from_key(key or name)
        if cls is None:
            continue
        out.append(
            {
                "class": cls,
                "skills": _skills(cskill),
                "source_book": book,
                "shape": "ability-key",
            }
        )
    return out


# ⚠️ I LIBRI FUORI DA `roleplaying_game/`. Misurato: li' dentro ci sono altri
# 218 file con CSKILL, ed e' dove vivono le prestige da Player Companion,
# Campaign Setting e Adventure Path (Living Monolith, Evangelist, Hinterlander).
# `BOOK_CLASS_FILES` copre solo i manuali base, per costruzione: qui si cammina
# l'albero invece di elencare i file, perche' quelle collane sono decine di
# volumi e un elenco a mano sarebbe vecchio dal giorno dopo.
#
# ⚠️ ORDINE: questi vengono DOPO i manuali base. Il consumatore tiene la PRIMA
# voce per classe, quindi una definizione del manuale batte una variante da AP.
EXTRA_TREES = ["player_companion", "campaign_setting", "adventure_path"]


def _extra_files(pcgen_root: Path) -> list[tuple[str, Path]]:
    """(etichetta, file) per i libri fuori da roleplaying_game."""
    out: list[tuple[str, Path]] = []
    for tree in EXTRA_TREES:
        radice = pcgen_root / DATA_SUBDIR / tree
        if not radice.is_dir():
            continue
        for path in sorted(radice.rglob("*.lst")):
            nome = path.name
            if nome.endswith("_classes.lst") or "abilities_class" in nome:
                out.append((f"{tree}/{path.parent.name}", path))
    return out


def build(pcgen_root: Path) -> dict:
    entries: list[dict] = []
    counts: dict[str, int] = {}
    for book, cfg in BOOK_CLASS_FILES.items():
        book_dir = pcgen_root / DATA_SUBDIR / cfg["dir"]
        found: list[dict] = []
        for rel in cfg.get("classes", []):
            path = book_dir / rel
            if path.is_file():
                found += from_classes_file(
                    path.read_text(encoding="utf-8", errors="replace"), book
                )
        for rel in cfg.get("abilities", []):
            path = book_dir / rel
            if path.is_file():
                found += from_abilities_file(
                    path.read_text(encoding="utf-8", errors="replace"), book
                )
        entries += found
        counts[book] = len(found)

    extra = 0
    for etichetta, path in _extra_files(pcgen_root):
        testo = path.read_text(encoding="utf-8", errors="replace")
        trovate = (
            from_classes_file(testo, etichetta)
            if path.name.endswith("_classes.lst")
            else from_abilities_file(testo, etichetta)
        )
        entries += trovate
        extra += len(trovate)
    counts["(altre collane)"] = extra

    return {
        "_provenance": {
            "source": (
                "PCGen data sets (github.com/PCGen/pcgen), "
                f"{DATA_SUBDIR}/roleplaying_game/*"
            ),
            "pcgen_commit": _pcgen_commit(pcgen_root),
            "generated_by": "Master-DD-Taverna/tools/import_pcgen_class_skills.py",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": LICENSE_TEXT,
            "note": (
                "solo il tag CSKILL: nomi di abilita' di classe. I marcatori "
                "di famiglia (TYPE=Craft/Knowledge/Profession) restano come "
                "stanno: espanderli e' una decisione del consumatore."
            ),
        },
        "counts": counts,
        "entries": entries,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pcgen-repo", default=str(DEFAULT_PCGEN_REPO))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    pcgen_root = Path(args.pcgen_repo)
    if not (pcgen_root / DATA_SUBDIR).is_dir():
        print(f"clone PCGen non trovato: {pcgen_root / DATA_SUBDIR}", file=sys.stderr)
        return 1

    payload = build(pcgen_root)
    distinte = {e["class"] for e in payload["entries"]}
    print(
        f"CSKILL: {len(payload['entries'])} voci, {len(distinte)} classi distinte "
        f"(commit pcgen {payload['_provenance']['pcgen_commit'][:12]})"
    )
    for book, n in payload["counts"].items():
        print(f"  {book}: {n}")

    if args.report_only:
        return 0

    out = Path(args.out_dir) / OUTPUT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"scritto {out} ({len(payload['entries'])} voci)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
