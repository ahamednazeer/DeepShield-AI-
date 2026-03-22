from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlparse


def has_timm() -> bool:
    return importlib.util.find_spec("timm") is not None


def _candidate_filenames(model_name: str) -> tuple[object, list[str]]:
    import timm

    pretrained_cfg = timm.get_pretrained_cfg(model_name)
    candidates: list[str] = []

    hf_filename = getattr(pretrained_cfg, "hf_hub_filename", None)
    if hf_filename:
        candidates.append(hf_filename)

    url = getattr(pretrained_cfg, "url", None) or ""
    url_filename = Path(urlparse(url).path).name if url else ""
    if url_filename:
        candidates.append(url_filename)

    for filename in ("model.safetensors", "pytorch_model.bin"):
        if filename not in candidates:
            candidates.append(filename)

    return pretrained_cfg, candidates


def _find_hf_cache_file(repo_id: str, filenames: list[str]) -> Path | None:
    cache_root = Path(os.getenv("HF_HUB_CACHE", str(Path.home() / ".cache" / "huggingface" / "hub")))
    repo_dir = cache_root / f"models--{repo_id.replace('/', '--')}"
    if not repo_dir.exists():
        return None

    for filename in filenames:
        if not filename:
            continue
        for candidate in repo_dir.glob(f"snapshots/*/{filename}"):
            if candidate.exists():
                return candidate
        for candidate in repo_dir.glob(f"**/{filename}"):
            if candidate.exists():
                return candidate
    return None


def _find_torch_cache_file(filenames: list[str]) -> Path | None:
    try:
        import torch
    except Exception:
        return None

    checkpoints_dir = Path(torch.hub.get_dir()) / "checkpoints"
    if not checkpoints_dir.exists():
        return None

    for filename in filenames:
        if not filename:
            continue
        candidate = checkpoints_dir / filename
        if candidate.exists():
            return candidate.resolve()
    return None


def resolve_local_pretrained_timm_weights(model_name: str) -> Path | None:
    if not has_timm():
        return None

    pretrained_cfg, candidates = _candidate_filenames(model_name)
    repo_id = getattr(pretrained_cfg, "hf_hub_id", None)
    if repo_id:
        cached = _find_hf_cache_file(repo_id, candidates)
        if cached is not None:
            return cached

    return _find_torch_cache_file(candidates)


def pretrained_timm_available(model_name: str) -> tuple[bool, str | None]:
    if not has_timm():
        return False, "timm is not installed."
    weight_path = resolve_local_pretrained_timm_weights(model_name)
    if weight_path is None:
        return False, "Pretrained weights are not cached locally."
    return True, None


def create_local_pretrained_timm_model(model_name: str):
    weight_path = resolve_local_pretrained_timm_weights(model_name)
    if weight_path is None:
        raise RuntimeError(
            f"Pretrained weights for {model_name} are not cached locally. "
            "Download them once in an environment with internet access, then rerun."
        )

    import timm
    from timm.models import load_checkpoint

    model = timm.create_model(model_name, pretrained=False)
    load_checkpoint(model, str(weight_path), strict=True, weights_only=False)
    return model
