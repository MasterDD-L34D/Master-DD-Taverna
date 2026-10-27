"""Test per l'engine ComfyUI (F3, IMG-05): workflow builder + client HTTP."""

import io
import json
import sys
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.ml.comfy_workflows import build_workflow, MODELS
from src.ml.comfyui import ComfyUIEngine
from src.ml.imagine import ImagineUnavailable, get_imagine_engine


class FakeResp:
    def __init__(self, payload, binary=False):
        self._payload = payload
        self._binary = binary

    def read(self):
        return self._payload if self._binary else json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_workflow_sdxl_structure():
    wf = build_workflow("sdxl", "un dungeon", 512, 768, 42)
    # nodi chiave del grafico SDXL minimo
    assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
    assert wf["1"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert wf["2"]["inputs"]["text"] == "un dungeon"  # prompt positivo
    assert wf["4"]["inputs"]["width"] == 512
    assert wf["4"]["inputs"]["height"] == 768
    assert wf["5"]["class_type"] == "KSampler"
    assert wf["5"]["inputs"]["seed"] == 42
    assert wf["7"]["class_type"] == "SaveImage"


def test_workflow_unknown_model():
    with pytest.raises(ImagineUnavailable, match="workflow"):
        build_workflow("xyz", "p", 64, 64, 1)


def test_engine_generate_success(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else req
        calls.append(url)
        if url.endswith("/prompt"):
            return FakeResp({"prompt_id": "pid-1"})
        if "/history/" in url:
            return FakeResp(
                {
                    "pid-1": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "taverna_img_00001_.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if "/view" in url:
            return FakeResp(b"\x89PNG\r\n\x1a\nfakepng", binary=True)
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl")
    out = engine.generate("un dungeon", 512, 768, 42)
    assert out["png"].startswith(b"\x89PNG")
    assert (out["width"], out["height"]) == (512, 768)
    assert out["engine"] == "comfyui-sdxl"


def test_engine_unreachable_is_honest(monkeypatch):
    def boom(req, timeout=0):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl")
    with pytest.raises(ImagineUnavailable, match="run_nvidia_gpu"):
        engine.generate("p", 64, 64, 1)


def test_autostart_lancia_comfy_e_riprova(monkeypatch):
    """Server giu' + ML_IMG_COMFY_START_CMD: spawn + attesa readiness + retry."""
    monkeypatch.setenv("ML_IMG_COMFY_START_CMD", "cmd /c run_nvidia_gpu.bat")
    monkeypatch.setenv("ML_IMG_COMFY_START_CWD", "C:/comfy")
    monkeypatch.setenv("ML_IMG_COMFY_START_TIMEOUT_S", "5")
    spawned = []
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: spawned.append((a, k)) or type("P", (), {})(),
    )

    state = {"prompt_failed": False}

    def fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("/system_stats"):
            return FakeResp({"system": {}})
        if url.endswith("/prompt"):
            if not state["prompt_failed"]:
                state["prompt_failed"] = True  # primo tentativo: server giu'
                raise URLError("connection refused")
            return FakeResp({"prompt_id": "pid-1"})
        if "/history/" in url:
            return FakeResp(
                {
                    "pid-1": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "x.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if "/view" in url:
            return FakeResp(b"\x89PNG\r\n\x1a\nx", binary=True)
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl", poll_interval_s=0)
    out = engine.generate("p", 64, 64, 1)
    assert out["png"].startswith(b"\x89PNG")
    assert spawned, "Popen non invocato per l'autostart"


def test_autostart_fallito_restituisce_501(monkeypatch):
    """Autostart configurato ma il server non sale mai: 501 onesto finale."""
    monkeypatch.setenv("ML_IMG_COMFY_START_CMD", "cmd /c run_nvidia_gpu.bat")
    monkeypatch.setenv("ML_IMG_COMFY_START_TIMEOUT_S", "0")
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: type("P", (), {})())

    def boom(req, timeout=0):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl")
    with pytest.raises(ImagineUnavailable, match="run_nvidia_gpu"):
        engine.generate("p", 64, 64, 1)


def test_engine_poll_timeout(monkeypatch):
    def fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("/prompt"):
            return FakeResp({"prompt_id": "pid-9"})
        if "/history/" in url:
            return FakeResp({})  # mai pronto
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    engine = ComfyUIEngine(
        "http://127.0.0.1:8188", "sdxl", timeout_s=0, poll_interval_s=0
    )
    with pytest.raises(ImagineUnavailable, match="timeout"):
        engine.generate("p", 64, 64, 1)


def test_factory_comfyui_variants(monkeypatch):
    monkeypatch.setenv("ML_IMG_COMFY_URL", "http://127.0.0.1:8188")
    assert get_imagine_engine("comfyui").name == "comfyui-sdxl"  # default modello
    assert get_imagine_engine("comfyui-flux").name == "comfyui-flux"
    assert get_imagine_engine("comfyui-qwen").name == "comfyui-qwen"
    with pytest.raises(ImagineUnavailable, match="sconosciuto"):
        get_imagine_engine("comfyui-xyz")


LORAS_ENV = json.dumps(
    {
        "fantasy-map": {"file": "fantasy_map_v2.safetensors", "strength": 0.8},
    }
)


def test_workflow_sdxl_con_lora():
    lora = {"file": "fantasy_map_v2.safetensors", "strength": 0.8}
    wf = build_workflow("sdxl", "un dungeon", 512, 512, 7, lora=lora)
    # LoraLoader inserito dopo il checkpoint e riferito downstream
    lora_nodes = [n for n in wf.values() if n["class_type"] == "LoraLoader"]
    assert len(lora_nodes) == 1
    assert lora_nodes[0]["inputs"]["lora_name"] == "fantasy_map_v2.safetensors"
    assert lora_nodes[0]["inputs"]["strength_model"] == 0.8
    sampler = wf["5"]["inputs"]
    text_enc = wf["2"]["inputs"]
    assert sampler["model"][0] != "1"  # il modello arriva dal LoraLoader
    assert text_enc["clip"][0] != "1"


def test_workflow_senza_lora_resta_invariato():
    wf = build_workflow("sdxl", "p", 64, 64, 1)
    assert all(n["class_type"] != "LoraLoader" for n in wf.values())


def test_lora_registry_da_env(monkeypatch):
    from src.ml.comfyui import parse_loras

    monkeypatch.setenv("ML_IMG_LORAS", LORAS_ENV)
    loras = parse_loras()
    assert loras["fantasy-map"]["file"] == "fantasy_map_v2.safetensors"
    # alias sconosciuto: errore onesto
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl", loras=loras)
    with pytest.raises(ImagineUnavailable, match="lora sconosciuto"):
        engine.generate("p", 64, 64, 1, lora="non-esiste")


def test_lora_env_malformato(monkeypatch):
    from src.ml.comfyui import parse_loras

    monkeypatch.setenv("ML_IMG_LORAS", "{non e' json")
    with pytest.raises(ImagineUnavailable, match="ML_IMG_LORAS"):
        parse_loras()


def test_fake_engine_rifiuta_lora_onestamente():
    fake = get_imagine_engine("fake")
    with pytest.raises(ImagineUnavailable, match="lora"):
        fake.generate("p", 64, 64, 1, lora="qualcosa")


# --- negative prompt (IMG-08) ---


def test_workflow_sdxl_negative_prompt():
    wf = build_workflow(
        "sdxl", "un dungeon", 512, 512, 42, negative_prompt="griglia, watermark"
    )
    assert wf["3"]["inputs"]["text"] == "griglia, watermark"
    # omesso: resta la stringa vuota di prima
    wf2 = build_workflow("sdxl", "un dungeon", 512, 512, 42)
    assert wf2["3"]["inputs"]["text"] == ""


def test_workflow_negative_prompt_anche_sd35m_e_qwen():
    wf = build_workflow("sd35m", "p", 64, 64, 1, negative_prompt="neg")
    assert wf["4"]["inputs"]["text"] == "neg"
    wf = build_workflow("qwen", "p", 64, 64, 1, negative_prompt="neg")
    assert wf["5"]["inputs"]["text"] == "neg"


def test_engine_passa_negative_prompt_al_workflow(monkeypatch):
    posted = []

    def fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("/prompt"):
            posted.append(json.loads(req.data.decode())["prompt"])
            return FakeResp({"prompt_id": "pid-1"})
        if "/history/" in url:
            return FakeResp(
                {
                    "pid-1": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "x.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if "/view" in url:
            return FakeResp(b"\x89PNG\r\n\x1a\nx", binary=True)
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    engine = ComfyUIEngine("http://127.0.0.1:8188", "sdxl", poll_interval_s=0)
    engine.generate("p", 64, 64, 1, negative_prompt="griglia")
    assert posted[0]["3"]["inputs"]["text"] == "griglia"


def test_fake_engine_negative_prompt_cambia_seed():
    fake = get_imagine_engine("fake")
    a = fake.generate("p", 64, 64, 42)
    b = fake.generate("p", 64, 64, 42, negative_prompt="griglia")
    assert a["png"] != b["png"]
    # stesso (prompt, negative, seed) -> deterministico
    c = fake.generate("p", 64, 64, 42, negative_prompt="griglia")
    assert b["png"] == c["png"]


# --- override cfg/steps da registry LoRA (IMG-08) ---


def test_lora_cfg_steps_override_sul_sampler():
    lora = {"file": "l.safetensors", "strength": 0.8, "cfg": 5.0, "steps": 35}
    wf = build_workflow("sdxl", "p", 64, 64, 1, lora=lora)
    assert wf["5"]["inputs"]["cfg"] == 5.0
    assert wf["5"]["inputs"]["steps"] == 35


def test_lora_senza_override_lascia_i_default():
    lora = {"file": "l.safetensors", "strength": 0.8}
    wf = build_workflow("sdxl", "p", 64, 64, 1, lora=lora)
    assert wf["5"]["inputs"]["cfg"] == 7.0
    assert wf["5"]["inputs"]["steps"] == 25
