"""Workflow ComfyUI per i modelli img-gen (F3).

Ogni workflow e' un dict nel formato API di ComfyUI (POST /prompt): nodi
con class_type + inputs. Parametrizzati da (prompt, width, height, seed).
Aggiungere un modello = aggiungere una entry in MODELS con il suo builder.
LoRA (IMG-07): registry nominato via env ML_IMG_LORAS; quando richiesto si
inserisce un LoraLoader che patcha MODEL+CLIP a valle del loader base.
La entry puo' anche dichiarare "cfg"/"steps" consigliati dall'autore del
LoRA (IMG-08): applicati come override al KSampler, solo per quel LoRA.
Negative prompt (IMG-08): il nodo CLIPTextEncode negativo riceve il testo
passato dalla API (default ""); flux-schnell (cfg 1.0) lo ignora.
"""

from __future__ import annotations

from typing import Callable

LoraSpec = dict  # {"file": str, "strength": float, "cfg"?: float, "steps"?: int}


def _inject_lora(
    wf: dict, lora: LoraSpec, model_src: list, clip_src: list, node_id: str
) -> dict:
    """Inserisce un LoraLoader e rifia i riferimenti model/clip downstream."""
    wf[node_id] = {
        "class_type": "LoraLoader",
        "inputs": {
            "lora_name": lora["file"],
            "strength_model": lora["strength"],
            "strength_clip": lora["strength"],
            "model": list(model_src),
            "clip": list(clip_src),
        },
    }
    for nid, node in wf.items():
        if nid == node_id:
            continue
        for key, val in node["inputs"].items():
            if val == list(model_src):
                node["inputs"][key] = [node_id, 0]
            elif val == list(clip_src):
                node["inputs"][key] = [node_id, 1]
    return wf


def _apply_sampler_overrides(wf: dict, lora: LoraSpec) -> dict:
    """Override opzionali cfg/steps dal registry LoRA (IMG-08): alcuni LoRA
    dichiarano impostazioni consigliate dall'autore (es. battlemap: cfg 5,
    steps 35) che diventano parte del registry, non magic number nel workflow."""
    cfg, steps = lora.get("cfg"), lora.get("steps")
    if cfg is None and steps is None:
        return wf
    for node in wf.values():
        if node["class_type"] == "KSampler":
            if cfg is not None:
                node["inputs"]["cfg"] = cfg
            if steps is not None:
                node["inputs"]["steps"] = steps
    return wf


def _sdxl(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    lora: LoraSpec | None = None,
    negative_prompt: str = "",
) -> dict:
    wf = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 25,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "taverna_img", "images": ["6", 0]},
        },
    }
    if lora:
        _inject_lora(wf, lora, ["1", 0], ["1", 1], "8")
    return wf


def _flux(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    lora: LoraSpec | None = None,
    negative_prompt: str = "",
) -> dict:
    # FLUX.1-schnell GGUF: UnetLoaderGGUF + DualCLIPLoader + VAE dedicato.
    # N.B. schnell gira a cfg=1.0: il negative non viene usato (input negative
    # cablato sul positivo); negative_prompt e' accettato ma ignorato qui.
    wf = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "flux1-schnell-Q4_K_S.gguf"},
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux",
            },
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["3", 0]},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "taverna_img", "images": ["7", 0]},
        },
    }
    if lora:
        _inject_lora(wf, lora, ["1", 0], ["2", 0], "9")
    return wf


def _sd35m(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    lora: LoraSpec | None = None,
    negative_prompt: str = "",
) -> dict:
    # SD 3.5 Medium GGUF: UnetLoaderGGUF + TripleCLIPLoader + VAE 16ch
    # dedicata (la GGUF non la include; quella SDXL a 4 canali NON decodifica
    # i latent SD3 a 16 canali — bug smoke IMG-06). Latent: EmptySD3LatentImage.
    wf = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "sd3.5_medium-Q4_K_S.gguf"},
        },
        "2": {
            "class_type": "TripleCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "clip_g.safetensors",
                "clip_name3": "t5xxl_fp8_e4m3fn.safetensors",
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 25,
                "cfg": 4.5,
                "sampler_name": "euler",
                "scheduler": "sgm_uniform",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        "9": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "sd35_vae.safetensors"},
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["9", 0]},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "taverna_img", "images": ["7", 0]},
        },
    }
    if lora:
        _inject_lora(wf, lora, ["1", 0], ["2", 0], "10")
    return wf


def _qwen(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    lora: LoraSpec | None = None,
    negative_prompt: str = "",
) -> dict:
    # Qwen-Image GGUF: UnetLoaderGGUF + CLIPLoaderGGUF (VL 7B GGUF — il
    # fp8_scaled safetensors NON si mixa con unet GGUF, bug smoke IMG-06)
    # + VAE dedicato.
    wf = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "Qwen_Image-Q4_K_S.gguf"},
        },
        "2": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {
                "clip_name": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
                "type": "qwen_image",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "qwen_image_vae.safetensors"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["2", 0]},
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 20,
                "cfg": 2.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "taverna_img", "images": ["8", 0]},
        },
    }
    if lora:
        _inject_lora(wf, lora, ["1", 0], ["2", 0], "10")
    return wf


MODELS: dict[str, Callable[..., dict]] = {
    "sdxl": _sdxl,
    "flux": _flux,
    "sd35m": _sd35m,
    "qwen": _qwen,
}


def build_workflow(
    model: str,
    prompt: str,
    width: int,
    height: int,
    seed: int,
    lora: LoraSpec | None = None,
    negative_prompt: str = "",
) -> dict:
    from src.ml.imagine import ImagineUnavailable

    builder = MODELS.get(model)
    if not builder:
        raise ImagineUnavailable(
            f"workflow sconosciuto: {model!r} (attesi: {', '.join(MODELS)})"
        )
    wf = builder(
        prompt, width, height, seed, lora=lora, negative_prompt=negative_prompt
    )
    if lora:
        _apply_sampler_overrides(wf, lora)
    return wf
