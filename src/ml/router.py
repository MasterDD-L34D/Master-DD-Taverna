"""Router /ml (REF-09 v1): POST /ml/transcribe + GET /ml/health.
F3: POST /ml/imagine + GET /ml/imagine/{imageId} (contratto img-gen-design:
registry engine via env, 501 onesto, WORM content-addressed).

Contratto output 1:1 con transcriptImportSchema di pathmaster (ADR-C2).
Audio originale in WORM storage (REQ-001). Consenso: gate lato pathmaster
(REQ-002), questo servizio e' un transcodificatore dumb.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from src.ml.asr import AsrUnavailable, get_asr_engine
from src.ml.imagine import ImagineUnavailable, get_imagine_engine
from src.ml.storage import save_audio_worm, save_image_manifest, save_image_worm

router = APIRouter(prefix="/ml", tags=["ml"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB: sessioni da ore restano fuori v1


def _audio_dir() -> Path:
    """Directory WORM dell'audio (letta a ogni richiesta: i test la variano
    via env; la costante import-time la congelerebbe al primo import)."""
    return Path(
        os.environ.get(
            "ML_AUDIO_DIR",
            Path(__file__).resolve().parents[1] / "data" / "ml" / "audio",
        )
    )


def _image_dir() -> Path:
    """Directory WORM delle immagini generate (stessa disciplina di _audio_dir)."""
    return Path(
        os.environ.get(
            "ML_IMG_DIR", Path(__file__).resolve().parents[1] / "data" / "ml" / "images"
        )
    )


@router.get("/health")
def ml_health():
    engine = os.environ.get("ML_ASR_ENGINE", "fake")
    img_engine = os.environ.get("ML_IMG_ENGINE", "off")
    return {
        "status": "ok",
        "engine": engine,
        "img_engine": img_engine,
        "scope": "asr-v1+img-v1",
    }


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), diarize: bool = Form(False)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "file vuoto")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file oltre {MAX_UPLOAD_BYTES} byte (v1)")
    save_audio_worm(data, file.filename or "audio.bin", _audio_dir())
    try:
        engine = get_asr_engine()
        return engine.transcribe(data, file.filename or "audio.bin", diarize=diarize)
    except AsrUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc


class ImagineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    width: int = Field(default=1024, ge=64, le=1536)
    height: int = Field(default=1024, ge=64, le=1536)
    seed: int | None = None
    engine: str | None = None  # override puntuale (es. testare flux con env=fake)
    lora: str | None = None  # alias dal registry ML_IMG_LORAS (solo comfyui)
    negative_prompt: str | None = Field(default=None, max_length=2000)


@router.post("/imagine")
def imagine(req: ImagineRequest):
    try:
        engine = get_imagine_engine(req.engine)
        result = engine.generate(
            req.prompt,
            req.width,
            req.height,
            req.seed,
            lora=req.lora,
            negative_prompt=req.negative_prompt,
        )
    except ImagineUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    image_dir = _image_dir()
    _, sha, image_id = save_image_worm(result["png"], image_dir)
    save_image_manifest(
        image_id,
        {
            "prompt": req.prompt,
            "seed": req.seed,
            "engine": result["engine"],
            "width": result["width"],
            "height": result["height"],
            "sha256": sha,
            "lora": req.lora,
            "negative_prompt": req.negative_prompt,
        },
        image_dir,
    )
    return {
        "imageId": image_id,
        "sha256": sha,
        "mimeType": "image/png",
        "width": result["width"],
        "height": result["height"],
        "engine": result["engine"],
    }


@router.get("/imagine/{image_id}")
def imagine_get(image_id: str):
    if not re.fullmatch(r"img_[0-9a-f]{16}", image_id):
        raise HTTPException(400, "imageId malformato")
    path = _image_dir() / f"{image_id}.png"
    if not path.exists():
        raise HTTPException(404, "immagine non trovata")
    return Response(content=path.read_bytes(), media_type="image/png")
