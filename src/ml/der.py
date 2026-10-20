"""Misura DER semplificata (E3, REQ-010): attribution error su griglia fine.

Ispirata al DER standard NIST (md-eval), implementazione in casa (solo
stdlib): le etichette ipotesi "S1".."Sn" sono anonime, quindi si cerca il
mapping ottimo ipotesi->reference prima di contare gli errori. Il mapping
ottimo e' un linear assignment puro: con le tabelle di `_precompute`,
miss+fa+confusion = speaker-time ref + tick ipotesi - 2 x co-attivazioni del
mapping, cioe' minimizzare l'errore equivale a massimizzare la somma delle
co-attivazioni. Si risolve con l'algoritmo ungherese O(n^2 m) — la forza
bruta sui mapping (6^5 assegnazioni x 120k tick, rilievo Codex 2026-10-20)
non scala su sessioni reali da 15-30 minuti. Semplificazioni documentate
rispetto al NIST formale:

- niente collare di tolleranza ai confini segmento (forgiveness collar);
- griglia temporale fissa (default 10 ms) invece di integrazione continua;
- overlap: ogni speaker di reference attivo sul tick contribuisce al
  denominatore (speaker-time), come NIST; per ogni speaker ref attivo senza il
  suo corrispondente ipotesi mappato attivo si conta miss (nessuna ipotesi sul
  tick) o confusion (ipotesi attiva ma speaker sbagliato);
- false alarm: ogni speaker ipotesi attivo il cui mapping non punta a uno
  speaker ref attivo sul tick.

DER = (miss + false_alarm + confusion) / speaker-time reference.

NON e' il gate formale REQ-010: quello richiede audio reale di sessione.
"""
from __future__ import annotations

import math

DEFAULT_TICK_SECONDS = 0.01


def _grid(segments, tick, n_ticks):
    """set di speaker attivi per tick (indice = int(start/tick))."""
    grid = [set() for _ in range(n_ticks)]
    for seg in segments:
        a = int(seg["start"] / tick)
        b = int(math.ceil(seg["end"] / tick))
        for i in range(max(a, 0), min(b, n_ticks)):
            grid[i].add(seg["speaker"])
    return grid


def _precompute(ref_grid, hyp_grid):
    """Conteggi per-tick in UN passaggio: co-attivazioni (s,h), tick per
    speaker, tick con ref attivo e ipotesi vuota. Il costo della misura sta
    nella griglia (10 ms x minuti): precomputare qui e valutare il mapping su
    queste tabelle rende lo scoring O(#speaker) invece di O(#tick)."""
    co: dict = {}
    ref_ticks: dict = {}
    hyp_ticks: dict = {}
    ref_hyp_empty: dict = {}
    scored = 0
    for ref_set, hyp_set in zip(ref_grid, hyp_grid):
        scored += len(ref_set)
        for s in ref_set:
            ref_ticks[s] = ref_ticks.get(s, 0) + 1
            if not hyp_set:
                ref_hyp_empty[s] = ref_hyp_empty.get(s, 0) + 1
            for h in hyp_set:
                co[(s, h)] = co.get((s, h), 0) + 1
        for h in hyp_set:
            hyp_ticks[h] = hyp_ticks.get(h, 0) + 1
    return co, ref_ticks, hyp_ticks, ref_hyp_empty, scored


def _score_precomputed(pre, mapping):
    """Conteggi errore per un mapping ipotesi->reference (None = non mappato),
    dalle tabelle di `_precompute`. Stessa semantica dello scoring su griglia:
    correct = co-attivazioni; dei tick restanti dello speaker ref, miss se
    l'ipotesi e' vuota, confusion altrimenti; fa = tick ipotesi il cui mapping
    non punta a uno speaker ref attivo."""
    co, ref_ticks, hyp_ticks, ref_hyp_empty, scored = pre
    inv = {v: k for k, v in mapping.items() if v is not None}
    correct = miss = fa = confusion = 0
    for s, n in ref_ticks.items():
        h = inv.get(s)
        c = co.get((s, h), 0) if h is not None else 0
        correct += c
        rest = n - c  # s attivo senza la sua ipotesi mappata
        e = ref_hyp_empty.get(s, 0)  # di questi: tick con ipotesi vuota
        miss += e
        confusion += rest - e
    for h, n in hyp_ticks.items():
        s = mapping.get(h)
        fa += n if s is None else n - co.get((s, h), 0)
    return correct, miss, fa, confusion, scored


def _assegnazione_ottima(profit):
    """Algoritmo ungherese (potenziali, O(n^2 m)) per il massimo profitto.

    `profit`: matrice n righe x m colonne con n <= m. Ritorna dict
    riga -> colonna. Schema standard (cp-algorithms), costi = -profit."""
    n = len(profit)
    m = len(profit[0])
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)  # p[j] = riga assegnata alla colonna j
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [math.inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = math.inf
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = -profit[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    return {p[j] - 1: j - 1 for j in range(1, m + 1) if p[j] != 0}


def compute_der(ref_segments, hyp_segments, tick=DEFAULT_TICK_SECONDS):
    """DER fra reference (ground truth) e ipotesi (segmenti con `speaker`).

    ref/hyp: liste di {"start": float, "end": float, "speaker": str}.
    Ritorna dict con der, componenti (miss/false_alarm/confusion/correct in
    tick), scored_seconds (speaker-time reference) e mapping ottimo trovato."""
    if not ref_segments:
        raise ValueError("reference vuota: niente speaker-time da misurare")
    n_ticks = max(1, int(math.ceil(
        max(s["end"] for s in ref_segments + hyp_segments) / tick)))
    ref_grid = _grid(ref_segments, tick, n_ticks)
    hyp_grid = _grid(hyp_segments, tick, n_ticks)
    ref_labels = sorted({s["speaker"] for s in ref_segments})
    hyp_labels = sorted({s["speaker"] for s in hyp_segments})
    pre = _precompute(ref_grid, hyp_grid)
    co = pre[0]
    # Colonne: speaker ref + una colonna dummy per OGNI ipotesi (profitto 0),
    # cosi' l'ungherese puo' lasciare non mappata qualunque ipotesi — come il
    # None della vecchia enumerazione.
    colonne = ref_labels + [None] * len(hyp_labels)
    mapping = dict.fromkeys(hyp_labels)
    if hyp_labels:
        profit = [
            [co.get((s, h), 0) if s is not None else 0 for s in colonne]
            for h in hyp_labels
        ]
        for row, colonna in _assegnazione_ottima(profit).items():
            mapping[hyp_labels[row]] = colonne[colonna]
    correct, miss, fa, confusion, scored = _score_precomputed(pre, mapping)
    return {
        "der": (miss + fa + confusion) / max(1, scored),
        "miss": miss,
        "false_alarm": fa,
        "confusion": confusion,
        "correct": correct,
        "scored_seconds": round(scored * tick, 3),
        "tick_seconds": tick,
        "mapping": mapping,
    }
