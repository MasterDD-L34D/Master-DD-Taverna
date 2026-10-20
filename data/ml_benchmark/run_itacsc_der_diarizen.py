#!/usr/bin/env python3
"""Misura DER con DiariZen sulle conversazioni ASR-ItaCSC (P6, braccio B').

Stesso metodo di run_itacsc_der.py (mix mono gia' pronti, ground truth dalle
annotazioni, harness src.ml.der.compute_der), ma la diarizzazione e'
DiariZen (BUTSpeechFIT, MIT) invece di resemblyzer.

Perche' DiariZen e non pyannote: speaker-diarization-3.1 e community-1 sono
GATED su Hugging Face (serve account + token). DiariZen no. E nel benchmark
pubblicato (README repo, niente collar, stessi dataset) DiariZen batte
pyannote 3.1 ovunque: DIHARD3 14,5% vs 21,7%, VoxConverse 9,1% vs 11,3%,
AMI-SDM 13,9% vs 22,4%.

Ambiente: venv C:/dev/pathfinder/tooling/p6-audio (torch 2.5.1 cpu,
torchaudio 2.5.1, fork pyannote-audio di DiariZen in editable — il pin
ufficiale torch 2.1.1 non ha wheel per Python 3.12).

Uso (dalla radice del repo Taverna)::

    C:/dev/pathfinder/tooling/p6-audio/Scripts/python.exe \
        data/ml_benchmark/run_itacsc_der_diarizen.py [A0001_S001 ...]

Confronto diretto col braccio A (resemblyzer, commit 8fd3726):
A0001_S001 53,3% / A0002_S006 81,0% / A0003_S001 38,8%, media 57,7%.
"""
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ml.der import compute_der
from data.ml_benchmark.prepare_itacsc_groundtruth import (
    build_ground_truth, conversation_txt_names, parse_turns)

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "itacsc"
ZIP_PATH = DATA_DIR / "Italian_Conversational_Speech_Corpus.zip"
MODEL = "BUT-FIT/diarizen-wavlm-base-s80-md"

CONVERSATIONS = ["A0001_S001", "A0002_S006", "A0003_S001"]


def _wav_fingerprint(wav: Path) -> dict:
    """Impronta del mix (dimensione + mtime): la cache della diarizzazione
    vale solo per QUESTO wav — un mix rigenerato (altro --max-seconds, altra
    sorgente) invalida i segmenti salvati, altrimenti il DER confronterebbe
    ipotesi stantie."""
    st = wav.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def _wav_seconds(wav: Path) -> float:
    """Durata reale del mix: la finestra della ground truth e' questa, non
    una costante — un mix piu' corto aggiungerebbe miss inventati, uno piu'
    lungo falsi allarmi."""
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def diarize(pipeline, wav: Path, conv: str) -> list[dict]:
    """Segmenti ipotesi nel formato atteso da compute_der (cache su json,
    legata all'impronta del wav e al modello)."""
    out_json = DATA_DIR / f"diarizen_{conv}.json"
    if out_json.exists():
        cache = json.loads(out_json.read_text(encoding="utf-8"))
        if (cache.get("model") == MODEL
                and cache.get("wav") == _wav_fingerprint(wav)):
            return cache["segments"]
    result = pipeline(str(wav), sess_name=conv)
    segments = [
        {"start": turn.start, "end": turn.end, "speaker": speaker}
        for turn, _, speaker in result.itertracks(yield_label=True)
    ]
    out_json.write_text(
        json.dumps({"model": MODEL, "wav": _wav_fingerprint(wav),
                    "segments": segments},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return segments


def main() -> None:
    import zipfile

    from diarizen.pipelines.inference import DiariZenPipeline

    pipeline = DiariZenPipeline.from_pretrained(MODEL, rttm_out_dir=None)
    results = []
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for conv in (sys.argv[1:] or CONVERSATIONS):
            wav = DATA_DIR / f"{conv}_mix.wav"
            if not wav.exists():
                raise SystemExit(f"mix mancante: {wav} (lancia prima "
                                 "run_itacsc_der.py per generarlo)")
            tracks = [parse_turns(zf.read(n).decode("utf-8"))
                      for n in conversation_txt_names(zf, conv)]
            gt = build_ground_truth(tracks, max_seconds=_wav_seconds(wav))
            hyp = diarize(pipeline, wav, conv)
            r = compute_der(gt["segments"], hyp)
            results.append(r)
            print(f"{conv}: DER {r['der']:.1%} "
                  f"(scored {r['scored_seconds']:.1f}s, miss {r['miss']}, "
                  f"fa {r['false_alarm']}, confusion {r['confusion']}; "
                  f"mapping {r['mapping']}; ref {len(gt['segments'])} turni, "
                  f"hyp {len(hyp)} segmenti)", flush=True)
    if len(results) > 1:
        mean = sum(r["der"] for r in results) / len(results)
        print(f"media DER su {len(results)} conversazioni: {mean:.1%}")


if __name__ == "__main__":
    main()
