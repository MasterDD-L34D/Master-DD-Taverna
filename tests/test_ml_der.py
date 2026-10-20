"""Test per src/ml/der.py — harness DER su input sintetici noti (niente
modello reale: segmenti costruiti a mano, stesso pattern dei test diarize)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ml.der import compute_der


def _seg(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


def test_perfect_match_der_zero():
    ref = [_seg(0.0, 2.0, "A"), _seg(2.0, 4.0, "B")]
    hyp = [_seg(0.0, 2.0, "S1"), _seg(2.0, 4.0, "S2")]
    r = compute_der(ref, hyp)
    assert r["der"] == 0.0
    assert r["mapping"] == {"S1": "A", "S2": "B"}
    assert r["scored_seconds"] == 4.0


def test_mapping_is_optimal_not_positional():
    """Le etichette ipotesi sono anonime: S1->B, S2->A va trovato dal
    mapping ottimo (DER 0 anche con l'ordine scambiato)."""
    ref = [_seg(0.0, 2.0, "master"), _seg(2.0, 4.0, "player")]
    hyp = [_seg(0.0, 2.0, "S2"), _seg(2.0, 4.0, "S1")]
    r = compute_der(ref, hyp)
    assert r["der"] == 0.0
    assert r["mapping"] == {"S2": "master", "S1": "player"}


def test_known_confusion_and_false_alarm():
    """ref A[0,2] B[2,4], ipotesi un solo speaker S1 su [0,4]: meta'
    corretta, poi confusion (B parlava, ipotesi dice S1) + false alarm
    (S1 attivo ma A non parla). 200 tick corretti + 200 conf + 200 fa."""
    ref = [_seg(0.0, 2.0, "A"), _seg(2.0, 4.0, "B")]
    hyp = [_seg(0.0, 4.0, "S1")]
    r = compute_der(ref, hyp)
    assert r["correct"] == 200
    assert r["confusion"] == 200
    assert r["false_alarm"] == 200
    assert r["miss"] == 0
    assert r["der"] == pytest.approx(1.0)


def test_known_miss():
    """ref A[0,2], ipotesi solo [0,1]: meta' dello speaker-time perso."""
    r = compute_der([_seg(0.0, 2.0, "A")], [_seg(0.0, 1.0, "S1")])
    assert r["miss"] == 100
    assert r["der"] == pytest.approx(0.5)


def test_overlap_counts_speaker_time():
    """Overlap in reference: ogni speaker attivo conta nel denominatore
    (A[0,2] + B[1,3] = 4 s di speaker-time su 3 s di audio)."""
    ref = [_seg(0.0, 2.0, "A"), _seg(1.0, 3.0, "B")]
    hyp = [_seg(0.0, 2.0, "S1"), _seg(1.0, 3.0, "S2")]
    r = compute_der(ref, hyp)
    assert r["scored_seconds"] == 4.0
    assert r["der"] == 0.0


def test_empty_hypothesis_is_all_miss():
    r = compute_der([_seg(0.0, 1.0, "A")], [])
    assert r["der"] == pytest.approx(1.0)
    assert r["miss"] == 100


def test_empty_reference_raises():
    with pytest.raises(ValueError):
        compute_der([], [_seg(0.0, 1.0, "S1")])


def test_hungarian_matches_brute_force_optimum():
    """Parita' con la forza bruta: il mapping ungherese deve raggiungere lo
    STESSO errore minimo dell'enumerazione esaustiva (su un caso con overlap,
    miss, fa e confusion insieme). La forza bruta vive solo qui, come oracolo
    lento e ovvio contro cui si misura quello veloce; griglia e scoring sono
    quelli della libreria, quindi la parita' isola la sola scelta del mapping."""
    import itertools
    import math

    from src.ml.der import _grid, _precompute, _score_precomputed

    ref = [
        _seg(0.0, 2.0, "A"), _seg(1.0, 3.0, "B"), _seg(3.0, 5.0, "C"),
    ]
    hyp = [
        _seg(0.2, 2.2, "S1"), _seg(1.1, 2.8, "S2"),
        _seg(4.0, 6.0, "S3"),  # parte oltre la fine della ref: fa
    ]
    r = compute_der(ref, hyp)

    ref_labels = sorted({s["speaker"] for s in ref})
    hyp_labels = sorted({s["speaker"] for s in hyp})
    n_ticks = max(1, int(math.ceil(max(s["end"] for s in ref + hyp) / 0.01)))
    pre = _precompute(_grid(ref, 0.01, n_ticks), _grid(hyp, 0.01, n_ticks))
    best_err = min(
        sum(_score_precomputed(pre, dict(zip(hyp_labels, choice)))[1:4])
        for choice in itertools.product(ref_labels + [None], repeat=len(hyp_labels))
    )
    assert r["miss"] + r["false_alarm"] + r["confusion"] == best_err
