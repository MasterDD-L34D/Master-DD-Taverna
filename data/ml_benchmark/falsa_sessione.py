#!/usr/bin/env python3
"""Falsa sessione P6: registra -> diarizza (DiariZen) -> misura DER. Un comando.

Flusso (gate reale REQ-010: 15-30 min di gioco vero o simulato nella stanza
e col microfono che si useranno davvero, consensi REQ-002 spuntati prima):

1) RECORD:   registra dal microfono in wav 16 kHz mono
2) DIARIZE:  DiariZen -> segmenti + turni_ipotesi.tsv gia' precompilato
3) ANNOTA (manuale, l'unico passo umano): copia turni_ipotesi.tsv in
   turni_verita.tsv e correggi nomi/confini ascoltando il wav
4) DER:      confronto con l'harness src.ml.der (niente collar, overlap
             contato — stesso protocollo delle misure ItaCSC)

Uso (dalla radice del repo Taverna)::

    PY=C:/dev/pathfinder/tooling/p6-audio/Scripts/python.exe
    $PY data/ml_benchmark/falsa_sessione.py record  prova1 --minuti 20
    $PY data/ml_benchmark/falsa_sessione.py diarize prova1
    $PY data/ml_benchmark/falsa_sessione.py der     prova1

I file stanno in data/ml_benchmark/falsa_sessione/<nome>/ (gitignored:
audio personale, come itacsc/). Per fermare la registrazione prima del
tempo: Ctrl+C (il wav parziale e' comunque salvato e valido).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ml.der import compute_der

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE / "falsa_sessione"
SR = 16000
MODEL = "BUT-FIT/diarizen-wavlm-base-s80-md"


def cmd_record(name: str, minuti: float, device: int | None) -> None:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    out_dir = BASE_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "sessione.wav"
    if wav.exists():
        raise SystemExit(f"esiste gia': {wav} — scegli un altro nome")
    print(f"Registro {minuti:g} min dal microfono "
          f"{sd.query_devices(device or sd.default.device[0])['name']} "
          f"-> {wav}\nCtrl+C per fermare prima. Via tra 3 s...")
    sd.sleep(3000)
    n = int(minuti * 60 * SR)
    rec = sd.rec(n, samplerate=SR, channels=1, dtype="float32",
                 device=device)
    try:
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        # stima dei campioni effettivi non disponibile: rileggo lo stato
        print("\nRegistrazione interrotta: salvo il buffer (la coda puo' "
              "contenere silenzio — annota solo la parte parlata).")
    sf.write(str(wav), np.asarray(rec).reshape(-1), SR)
    print(f"Salvato {wav} ({wav.stat().st_size / 1e6:.1f} MB). "
          f"Prossimo passo: diarize {name}")


def cmd_diarize(name: str) -> None:
    out_dir = BASE_DIR / name
    wav = out_dir / "sessione.wav"
    if not wav.exists():
        raise SystemExit(f"manca {wav} — prima: record {name}")
    # La cache vale solo per QUESTO wav: una registrazione rifatta con lo
    # stesso nome (dimensione/mtime diverse) invalida i segmenti salvati,
    # altrimenti il DER confronterebbe ipotesi stantie.
    fingerprint = {"size": wav.stat().st_size, "mtime": int(wav.stat().st_mtime)}
    seg_json = out_dir / "segmenti_diarizen.json"
    if seg_json.exists():
        cache = json.loads(seg_json.read_text(encoding="utf-8"))
        if cache.get("model") == MODEL and cache.get("wav") == fingerprint:
            segments = cache["segments"]
        else:
            segments = None
    else:
        segments = None
    if segments is None:
        from diarizen.pipelines.inference import DiariZenPipeline
        pipeline = DiariZenPipeline.from_pretrained(MODEL, rttm_out_dir=None)
        result = pipeline(str(wav), sess_name=name)
        segments = [
            {"start": t.start, "end": t.end, "speaker": s}
            for t, _, s in result.itertracks(yield_label=True)
        ]
        seg_json.write_text(
            json.dumps({"model": MODEL, "wav": fingerprint,
                        "segments": segments},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    tsv = out_dir / "turni_ipotesi.tsv"
    with tsv.open("w", encoding="utf-8") as fh:
        for seg in segments:
            fh.write(f"{seg['start']:.2f}\t{seg['end']:.2f}\t{seg['speaker']}\n")
    speakers = sorted({s["speaker"] for s in segments})
    print(f"{len(segments)} segmenti, {len(speakers)} voci stimate "
          f"{speakers} -> {seg_json}")
    print(f"Turni precompilati in {tsv}\n"
          f"ORA IL PASSO UMANO: copia in turni_verita.tsv e correggi "
          f"nomi/confini ascoltando sessione.wav (Audacity: apri il wav, "
          f"leggi i secondi dalla timeline). Poi: der {name}")


def _load_tsv(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        start, end, speaker = line.split("\t")[:3]
        out.append({"start": float(start), "end": float(end),
                    "speaker": speaker})
    return out


def cmd_der(name: str) -> None:
    out_dir = BASE_DIR / name
    hyp_path = out_dir / "segmenti_diarizen.json"
    ref_path = out_dir / "turni_verita.tsv"
    if not ref_path.exists():
        raise SystemExit(f"manca {ref_path} — completa l'annotazione "
                         "(vedi output di diarize)")
    hyp = json.loads(hyp_path.read_text(encoding="utf-8"))["segments"]
    ref = _load_tsv(ref_path)
    r = compute_der(ref, hyp)
    print(f"{name}: DER {r['der']:.1%} "
          f"(scored {r['scored_seconds']:.1f}s speaker-time, "
          f"miss {r['miss']}, fa {r['false_alarm']}, "
          f"confusion {r['confusion']}; mapping {r['mapping']})")
    print("Soglie piano P6: <=20% GO | 20-30% GO condizionato | "
          ">30% NO-GO single-mic")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record", help="registra dal microfono")
    p.add_argument("name")
    p.add_argument("--minuti", type=float, default=20.0)
    p.add_argument("--device", type=int, default=None,
                   help="indice dispositivo da query_devices (default: "
                        "microfono predefinito di sistema)")
    p = sub.add_parser("diarize", help="DiariZen + turni precompilati")
    p.add_argument("name")
    p = sub.add_parser("der", help="DER ipotesi vs turni_verita.tsv")
    p.add_argument("name")
    args = ap.parse_args()
    if args.cmd == "record":
        cmd_record(args.name, args.minuti, args.device)
    elif args.cmd == "diarize":
        cmd_diarize(args.name)
    else:
        cmd_der(args.name)


if __name__ == "__main__":
    main()
