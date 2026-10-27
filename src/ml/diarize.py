"""Diarizzazione leggera (E3 v1, REQ-010): speaker labels sui segmenti whisper.

Embedding vocali resemblyzer (GE2E, modello MIT scaricato da GitHub, nessun
gate HuggingFace) + clustering in ordine temporale: ogni embedding va al
cluster piu' vicino se entro soglia coseno, altrimenti apre un cluster nuovo
(ABA riassegnato correttamente). Output: etichette "S1".."Sn" per segmento —
chiave `speaker` del contratto ADR-C2 (`speakerLabel` lato pathmaster).

Privacy (design E3): gli embedding sono calcolati in memoria e MAI persistiti;
il WORM contiene solo l'audio originale (REQ-001). Voiceprint persistente
(REQ-012) resta fuori scope v1: richiede design consenso/storage biometrico.
"""

from __future__ import annotations

import numpy as np

from src.ml.asr import AsrUnavailable, TranscriptSegment

MIN_SEG_SECONDS = 0.6  # sotto: embedding inaffidabile -> eredita l'etichetta
DEFAULT_THRESHOLD = 0.30  # distanza coseno per aprire un cluster nuovo


def _cosine_distance(a, b):
    return 1.0 - float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def _default_encoder():
    try:
        from resemblyzer import VoiceEncoder
    except ImportError as exc:
        raise AsrUnavailable(
            "resemblyzer non installato: pip install resemblyzer " "(o diarize=false)"
        ) from exc
    return VoiceEncoder()


def diarize_segments(
    wav, sample_rate, segments, threshold=DEFAULT_THRESHOLD, encoder=None
):
    """Etichette speaker per i segmenti whisper.

    wav: float32 mono a sample_rate Hz (come decode_audio di faster-whisper).
    segments: [{start, end, text, ...}] (secondi float). encoder: callable
    embed_utterance(clip) -> np.array (default: VoiceEncoder resemblyzer,
    lazy). Ritorna lista di "S1".."Sn" allineata ai segmenti; i segmenti piu'
    corti di MIN_SEG_SECONDS ereditano l'etichetta precedente."""
    if not segments:
        return []
    enc = encoder or _default_encoder()
    embs = []
    for seg in segments:
        a = int(seg["start"] * sample_rate)
        b = max(int(seg["end"] * sample_rate), a + 1)
        clip = wav[a:b]
        if len(clip) < int(MIN_SEG_SECONDS * sample_rate):
            embs.append(None)
        else:
            embs.append(enc.embed_utterance(clip))
    labels, centroids, counts = [], [], []
    for emb in embs:
        if emb is None:
            labels.append(None)
            continue
        if not centroids:
            centroids.append(emb.copy())
            counts.append(1)
            labels.append(0)
            continue
        dists = [_cosine_distance(emb, c) for c in centroids]
        best = int(np.argmin(dists))
        if dists[best] <= threshold:
            lab = best
        else:
            lab = len(centroids)
            centroids.append(emb.copy())
            counts.append(0)
        counts[lab] += 1
        centroids[lab] += (emb - centroids[lab]) / counts[lab]
        labels.append(lab)
    out, last = [], "S1"
    for lab in labels:
        if lab is not None:
            last = f"S{lab + 1}"
        out.append(last)
    return out


def attach_speakers(segments: list[TranscriptSegment], labels: list[str]):
    """Scrive la chiave speaker sui segmenti (in place, contratto ADR-C2)."""
    for seg, lab in zip(segments, labels):
        seg["speaker"] = lab
