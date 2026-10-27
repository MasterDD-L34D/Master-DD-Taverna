"""Test per data/ml_benchmark/prepare_itacsc_groundtruth.py — converter
TXT ItaCSC -> ground truth DER, su input giocattolo (niente dataset reale:
lo zip e' gitignored e non disponibile in CI)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.ml_benchmark.prepare_itacsc_groundtruth import build_ground_truth, parse_turns

TOY_TRACK_A = """\
[0.500,2.000]\tG0001\tfemale\tciao come stai
[2.500,4.000]\tG0001\tfemale\tbene grazie
[5.000,5.500]\t0\tnone\t[LAUGHTER]
riga non conforme da saltare
[9.000,8.000]\tG0001\tfemale\tturno degenere end<=start
"""
TOY_TRACK_B = """\
[1.000,3.000]\tG0002\tmale\te di dove sei\r
[4.500,6.000]\tG0002\tmale\tinteressante
"""


def test_parse_turns_keeps_only_speech():
    turns = parse_turns(TOY_TRACK_A)
    assert turns == [
        {"start": 0.5, "end": 2.0, "speaker": "G0001"},
        {"start": 2.5, "end": 4.0, "speaker": "G0001"},
    ]


def test_parse_turns_handles_crlf():
    turns = parse_turns(TOY_TRACK_B)
    assert turns[0]["speaker"] == "G0002"
    assert turns[0]["start"] == 1.0


def test_build_ground_truth_unione_ordinata():
    gt = build_ground_truth([parse_turns(TOY_TRACK_A), parse_turns(TOY_TRACK_B)])
    assert [s["speaker"] for s in gt["segments"]] == [
        "G0001",
        "G0002",
        "G0001",
        "G0002",
    ]
    # overlap naturale preservato: G0001 [0.5,2] e G0002 [1,3] convivono
    starts = [s["start"] for s in gt["segments"]]
    assert starts == sorted(starts)


def test_build_ground_truth_max_seconds_clampa_e_scarta():
    gt = build_ground_truth(
        [parse_turns(TOY_TRACK_A), parse_turns(TOY_TRACK_B)], max_seconds=3.0
    )
    assert gt["segments"] == [
        {"start": 0.5, "end": 2.0, "speaker": "G0001"},
        {"start": 1.0, "end": 3.0, "speaker": "G0002"},  # end clampato
        {"start": 2.5, "end": 3.0, "speaker": "G0001"},  # end clampato
    ]


def test_build_ground_truth_senza_turni_validi():
    gt = build_ground_truth([parse_turns("[1.0,2.0]\t0\tnone\t[MUSIC]")])
    assert gt["segments"] == []
