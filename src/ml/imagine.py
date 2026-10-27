"""Engine img-gen per il servizio /ml/imagine (F3, ratifica PRD §9.2).

Contratto: `docs/superpowers/specs/2026-07-26-img-gen-design.md` (repo
pathmaster-dd). Engine (env ML_IMG_ENGINE, default "off"):

- `off`  -> 501 onesto (nessun engine configurato);
- `fake` -> PNG deterministico da (prompt, seed, w, h), stdlib pura: per
  test e sviluppo offline. Si DICHIARA "fake" nel campo engine, mai
  spacciato per generazione reale;
- `flux` -> diffusers + FLUX.1-schnell (Apache 2.0), import lazy:
  dipendenza opzionale mancante -> 501 con istruzioni, mai traceback raw;
- `api`  -> provider esterno via ML_IMG_API_URL + ML_IMG_API_KEY (la key
  vive solo in env, MAI nei messaggi d'errore).
"""

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from typing import Protocol, TypedDict


class ImagineResult(TypedDict):
    png: bytes
    width: int
    height: int
    engine: str


class ImagineUnavailable(RuntimeError):
    """Engine richiesto ma non disponibile/configurato (501 onesto)."""


class ImagineEngine(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> ImagineResult: ...


def _seed_from(
    prompt: str, seed: int | None, negative_prompt: str | None = None
) -> int:
    """Il prompt entra SEMPRE nel seed (esplicito o meno): seed uguale su
    prompt diversi non deve dare immagini identiche. Vale anche per il
    negative prompt (IMG-08): cambia il condizionamento, quindi cambia seed."""
    material = f"{prompt}|{negative_prompt or ''}|{seed if seed is not None else ''}"
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


def _fake_png(seed: int, w: int, h: int) -> bytes:
    """PNG RGB deterministico: R da un LCG seedato, G/B gradienti."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    rows = bytearray()
    state = (seed & 0x7FFFFFFF) or 1
    for y in range(h):
        rows.append(0)  # filter byte
        for x in range(w):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            r = state % 256
            g = (x * 255) // max(w - 1, 1)
            b = (y * 255) // max(h - 1, 1)
            rows += bytes((r, g, b))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


class FakeImagineEngine:
    name = "fake"

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> ImagineResult:
        if lora:
            raise ImagineUnavailable("lora non supportato dall'engine fake")
        s = _seed_from(prompt, seed, negative_prompt)
        return {
            "png": _fake_png(s, width, height),
            "width": width,
            "height": height,
            "engine": self.name,
        }


class FluxImagineEngine:
    """Engine locale reale via diffusers (opt-in, import lazy)."""

    name = "flux"

    def __init__(self, model: str, device: str):
        try:
            import torch  # noqa: F401
            from diffusers import FluxPipeline
        except ImportError as exc:
            raise ImagineUnavailable(
                "diffusers/torch non installati: pip install diffusers torch "
                "transformers accelerate sentencepiece "
                "(o ML_IMG_ENGINE=fake per il mock)"
            ) from exc
        self._device = (
            "cuda"
            if device == "auto" and torch.cuda.is_available()
            else ("cpu" if device == "auto" else device)
        )
        dtype = torch.bfloat16 if self._device == "cuda" else torch.float32
        self._pipe = FluxPipeline.from_pretrained(model, torch_dtype=dtype)
        self._pipe.to(self._device)

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> ImagineResult:
        if lora:
            raise ImagineUnavailable(
                "lora via engine flux diretto non supportato: usa comfyui"
            )
        import io
        import torch

        generator = torch.Generator(device=self._device).manual_seed(
            _seed_from(prompt, seed, negative_prompt)
        )
        image = self._pipe(
            prompt,
            negative_prompt=negative_prompt or "",
            width=width,
            height=height,
            num_inference_steps=4,  # schnell: pochi step
            generator=generator,
        ).images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return {
            "png": buf.getvalue(),
            "width": width,
            "height": height,
            "engine": self.name,
        }


class ApiImagineEngine:
    """Provider esterno pluggabile. La key arriva SOLO da env e non finisce
    mai in messaggi d'errore/log."""

    name = "api"

    def __init__(self, base_url: str, api_key: str):
        if not base_url:
            raise ImagineUnavailable(
                "ML_IMG_ENGINE=api richiede ML_IMG_API_URL configurata"
            )
        self._base_url = base_url
        self._api_key = api_key

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> ImagineResult:
        if lora:
            raise ImagineUnavailable("lora non supportato dall'engine api")
        import json
        import urllib.error
        import urllib.request

        body = {"prompt": prompt, "width": width, "height": height}
        if seed is not None:
            body["seed"] = seed
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            self._base_url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                png = resp.read()
        except urllib.error.HTTPError as exc:
            raise ImagineUnavailable(f"provider immagini API: HTTP {exc.code}") from exc
        except OSError as exc:
            raise ImagineUnavailable(
                f"provider immagini API irraggiungibile ({self._base_url})"
            ) from exc
        if not png.startswith(b"\x89PNG"):
            raise ImagineUnavailable("provider immagini API: risposta non e' un PNG")
        return {"png": png, "width": width, "height": height, "engine": self.name}


def get_imagine_engine(force: str | None = None) -> ImagineEngine:
    kind = (force or os.environ.get("ML_IMG_ENGINE", "off")).strip().lower()
    if kind == "off":
        raise ImagineUnavailable(
            "nessun engine immagini configurato: imposta ML_IMG_ENGINE "
            "(fake|flux|api)"
        )
    if kind == "fake":
        return FakeImagineEngine()
    if kind == "flux":
        return FluxImagineEngine(
            model=os.environ.get("ML_IMG_MODEL", "black-forest-labs/FLUX.1-schnell"),
            device=os.environ.get("ML_IMG_DEVICE", "auto"),
        )
    if kind == "api":
        return ApiImagineEngine(
            base_url=os.environ.get("ML_IMG_API_URL", ""),
            api_key=os.environ.get("ML_IMG_API_KEY", ""),
        )
    if kind == "comfyui" or kind.startswith("comfyui-"):
        from src.ml.comfyui import DEFAULT_COMFY_URL, ComfyUIEngine

        model = (
            kind.removeprefix("comfyui-")
            if kind != "comfyui"
            else os.environ.get("ML_IMG_COMFY_MODEL", "sdxl")
        )
        from src.ml.comfyui import parse_loras

        return ComfyUIEngine(
            base_url=os.environ.get("ML_IMG_COMFY_URL", DEFAULT_COMFY_URL),
            model=model,
            loras=parse_loras(),
        )
    raise ImagineUnavailable(
        f"ML_IMG_ENGINE sconosciuto: {kind!r} "
        "(attesi: off, fake, flux, api, comfyui[-modello])"
    )
