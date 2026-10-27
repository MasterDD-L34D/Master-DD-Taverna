"""Engine ComfyUI (F3, IMG-05): Taverna parla al server ComfyUI locale via
HTTP API (POST /prompt + polling /history + GET /view). ComfyUI resta un
processo separato avviato al bisogno (run_nvidia_gpu.bat): se non risponde,
501 onesto con le istruzioni di avvio — mai un traceback raw.

Config: ML_IMG_COMFY_URL (default http://127.0.0.1:8188),
ML_IMG_COMFY_MODEL (default sdxl; anche suffix engine comfyui-<model>).
LoRA (IMG-07): registry nominato in ML_IMG_LORAS (JSON
{"alias": {"file": "...", "strength": 0.8}}), richiesto per-alias dalla API.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from src.ml.comfy_workflows import MODELS, build_workflow
from src.ml.imagine import ImagineUnavailable, _seed_from

DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

_UNREACHABLE_MSG = (
    "ComfyUI non raggiungibile su {base} (avvia: "
    "run_nvidia_gpu.bat in ComfyUI_windows_portable)"
)


class _ComfyDown(ImagineUnavailable):
    """Server non raggiungibile: il chiamante puo' tentare l'autostart."""


def parse_loras() -> dict:
    """Registry LoRA da env ML_IMG_LORAS (JSON alias -> {file, strength})."""
    raw = os.environ.get("ML_IMG_LORAS", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImagineUnavailable("ML_IMG_LORAS non e' JSON valido") from exc
    if not isinstance(data, dict):
        raise ImagineUnavailable(
            "ML_IMG_LORAS deve essere una mappa alias -> {file, strength}"
        )
    return data


class ComfyUIEngine:
    def __init__(
        self,
        base_url: str,
        model: str,
        loras: dict | None = None,
        timeout_s: int = 600,
        poll_interval_s: float = 1.0,
    ):
        if model not in MODELS:
            raise ImagineUnavailable(
                f"modello ComfyUI sconosciuto: {model!r} (attesi: {', '.join(MODELS)})"
            )
        if not base_url:
            raise ImagineUnavailable(
                "ML_IMG_ENGINE=comfyui richiede ML_IMG_COMFY_URL "
                "(es. http://127.0.0.1:8188)"
            )
        self._base = base_url.rstrip("/")
        self._model = model
        self._loras = loras if loras is not None else parse_loras()
        self._timeout_s = timeout_s
        self._poll_s = poll_interval_s
        self.name = f"comfyui-{model}"

    def _json(self, url: str, payload: dict | None = None):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"content-type": "application/json"} if payload is not None else {},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # errore applicativo (es. workflow invalido): il body spiega cosa
            try:
                body = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                body = ""
            raise ImagineUnavailable(
                f"ComfyUI: HTTP {exc.code} da {url.split(self._base)[-1]}: {body}"
            ) from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            raise _ComfyDown(_UNREACHABLE_MSG.format(base=self._base)) from exc

    def _is_up(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base}/system_stats", timeout=3):
                return True
        except Exception:
            return False

    def _autostart(self) -> bool:
        """Nota operativa F3: ComfyUI si avvia AL BISOGNO. Se
        ML_IMG_COMFY_START_CMD e' configurata, lo lancia e attende la
        readiness (polling /system_stats). Ritorna True se il server e' su."""
        cmd = os.environ.get("ML_IMG_COMFY_START_CMD", "")
        if not cmd:
            return False
        subprocess.Popen(
            cmd,
            cwd=os.environ.get("ML_IMG_COMFY_START_CWD") or None,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        timeout_s = int(os.environ.get("ML_IMG_COMFY_START_TIMEOUT_S", "180"))
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._is_up():
                return True
            time.sleep(max(self._poll_s, 0.5))
        return False

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> dict:
        try:
            return self._generate_once(
                prompt, width, height, seed, lora, negative_prompt
            )
        except _ComfyDown:
            if self._autostart():
                return self._generate_once(
                    prompt, width, height, seed, lora, negative_prompt
                )
            raise ImagineUnavailable(_UNREACHABLE_MSG.format(base=self._base))

    def _generate_once(
        self,
        prompt: str,
        width: int,
        height: int,
        seed: int | None,
        lora: str | None = None,
        negative_prompt: str | None = None,
    ) -> dict:
        seed_val = _seed_from(prompt, seed, negative_prompt)
        lora_spec = None
        if lora:
            lora_spec = self._loras.get(lora)
            if not lora_spec:
                raise ImagineUnavailable(
                    f"lora sconosciuto: {lora!r} (registry ML_IMG_LORAS: "
                    f"{', '.join(self._loras) or 'vuoto'})"
                )
        wf = build_workflow(
            self._model,
            prompt,
            width,
            height,
            seed_val,
            lora=lora_spec,
            negative_prompt=negative_prompt or "",
        )
        posted = self._json(f"{self._base}/prompt", {"prompt": wf})
        pid = posted.get("prompt_id")
        if not pid:
            raise ImagineUnavailable(
                f"ComfyUI: risposta /prompt senza prompt_id: {posted!r}"
            )

        deadline = time.monotonic() + self._timeout_s
        images = None
        while time.monotonic() < deadline:
            hist = self._json(f"{self._base}/history/{pid}")
            entry = hist.get(pid) if isinstance(hist, dict) else None
            if entry and entry.get("outputs"):
                for node_out in entry["outputs"].values():
                    if node_out.get("images"):
                        images = node_out["images"]
                        break
            if images:
                break
            time.sleep(self._poll_s)
        if not images:
            raise ImagineUnavailable(
                f"ComfyUI: timeout dopo {self._timeout_s}s in attesa del risultato"
            )

        img = images[0]
        qs = urllib.parse.urlencode(
            {
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            }
        )
        try:
            with urllib.request.urlopen(f"{self._base}/view?{qs}", timeout=60) as resp:
                png = resp.read()
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            raise ImagineUnavailable(
                "ComfyUI: impossibile scaricare l'immagine prodotta"
            ) from exc
        if not png.startswith(b"\x89PNG"):
            raise ImagineUnavailable("ComfyUI: l'output non e' un PNG")
        return {"png": png, "width": width, "height": height, "engine": self.name}
