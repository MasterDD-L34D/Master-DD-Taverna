"""Engine ASR per il servizio /ml/transcribe (REF-09 v1).

Contratto output: `transcriptImportSchema` di pathmaster (ADR-C2):
{"language": str, "segments": [{"start": float, "end": float, "text": str,
"confidence": float?}]} — secondi float, `speaker` omesso in v1 (predisposto
per la diarizzazione futura).

Engine: `faster_whisper` (reale, dipendenza opzionale) | `fake`
(deterministico, per test e sviluppo senza GPU/modello). Factory env-driven:
ML_ASR_ENGINE (default "fake"), ML_ASR_MODEL (default "small"),
ML_ASR_DEVICE (default "auto"), ML_ASR_COMPUTE_TYPE (default "int8").
"""

from __future__ import annotations

import os
from typing import Protocol, TypedDict


class TranscriptSegment(TypedDict, total=False):
    start: float
    end: float
    text: str
    confidence: float
    speaker: str  # presente solo con diarize=True (E3 v1)


class Transcript(TypedDict, total=False):
    language: str
    segments: list[TranscriptSegment]


class AsrUnavailable(RuntimeError):
    """Engine richiesto ma non disponibile (dipendenza opzionale mancante)."""


class AsrEngine(Protocol):
    def transcribe(
        self, audio: bytes, filename: str, diarize: bool = False
    ) -> Transcript: ...


class FakeAsrEngine:
    """Engine deterministico: 2 segmenti fissi calati sulla durata stimata.
    Con diarize=True assegna speaker finti (S1 alla parte 1, S2 alla 2)."""

    def transcribe(
        self, audio: bytes, filename: str, diarize: bool = False
    ) -> Transcript:
        dur = max(len(audio) / 16000.0, 1.0)  # stima grezza ~16KB/s
        segments: list[TranscriptSegment] = [
            {
                "start": 0.0,
                "end": round(dur / 2, 3),
                "text": f"[trascrizione simulata di {filename}, parte 1]",
                "confidence": 0.99,
            },
            {
                "start": round(dur / 2, 3),
                "end": round(dur, 3),
                "text": f"[trascrizione simulata di {filename}, parte 2]",
                "confidence": 0.98,
            },
        ]
        if diarize:
            segments[0]["speaker"] = "S1"
            segments[1]["speaker"] = "S2"
        return {"language": "it", "segments": segments}


class FasterWhisperEngine:
    """Engine reale via faster-whisper (import lazy: dipendenza opzionale)."""

    def __init__(self, model: str, device: str, compute_type: str):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AsrUnavailable(
                "faster-whisper non installato: pip install -r requirements-ml.txt "
                "(o ML_ASR_ENGINE=fake per il mock)"
            ) from exc
        self._model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(
        self, audio: bytes, filename: str, diarize: bool = False
    ) -> Transcript:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix="-" + filename, delete=False) as tmp:
            tmp.write(audio)
            tmp_path = tmp.name
        segments_out: list[TranscriptSegment] = []
        segments, info = self._model.transcribe(
            tmp_path, language="it", vad_filter=True
        )
        for seg in segments:
            entry: TranscriptSegment = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
            if seg.avg_logprob is not None:
                # logprob -> confidenza approssimata in [0,1] (clamp)
                entry["confidence"] = max(0.0, min(1.0, 1.0 + seg.avg_logprob))
            segments_out.append(entry)
        if not segments_out:
            raise AsrUnavailable(
                "faster-whisper: nessun segmento prodotto "
                "(audio muto o non decodificabile?)"
            )
        if diarize:
            from faster_whisper.audio import decode_audio
            from src.ml.diarize import attach_speakers, diarize_segments

            wav = decode_audio(tmp_path, sampling_rate=16000)
            attach_speakers(segments_out, diarize_segments(wav, 16000, segments_out))
        return {"language": info.language or "it", "segments": segments_out}


def get_asr_engine() -> AsrEngine:
    kind = os.environ.get("ML_ASR_ENGINE", "fake").strip().lower()
    if kind == "fake":
        return FakeAsrEngine()
    if kind == "faster_whisper":
        return FasterWhisperEngine(
            model=os.environ.get("ML_ASR_MODEL", "small"),
            device=os.environ.get("ML_ASR_DEVICE", "auto"),
            compute_type=os.environ.get("ML_ASR_COMPUTE_TYPE", "int8"),
        )
    raise AsrUnavailable(
        f"ML_ASR_ENGINE sconosciuto: {kind!r} " "(attesi: fake, faster_whisper)"
    )
