"""
Image Deepfake Detection Pipeline
Uses a CNN classifier plus heuristic forensic signals
(ELA, FFT, and color statistics).
"""

import io
import inspect
import json
import os
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageFilter
from scipy.fft import fft2, fftshift

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def _resolve_default_model_path() -> Path:
    override = os.getenv("IMAGE_MODEL_PATH")
    if override:
        return Path(override)

    for candidate in (
        "final_model.keras",
        "deepfake_cnn.keras",
        "deepfake.keras",
        "model.h5",
        "deepfake20.h5",
    ):
        path = MODELS_DIR / candidate
        if path.exists():
            return path

    return MODELS_DIR / "deepfake.keras"


MODEL_PATH = _resolve_default_model_path()
MODEL_IMAGE_SIZE = int(os.getenv("IMAGE_MODEL_IMAGE_SIZE", "224" if MODEL_PATH.name.endswith(".keras") else "256"))
MODEL_WEIGHT = float(os.getenv("IMAGE_MODEL_WEIGHT", "0.6"))
HEURISTIC_WEIGHT = float(os.getenv("IMAGE_HEURISTIC_WEIGHT", "0.4"))
MODEL_PREPROCESS = os.getenv("IMAGE_MODEL_PREPROCESS", "rescale").lower()
PIPELINE_MODE = os.getenv("IMAGE_PIPELINE_MODE", "multimodal_fusion").lower()
MODEL_REFERENCE_IMPL = os.getenv("IMAGE_REFERENCE_IMPL", "keras").lower()
TORCH_MODEL_NAME = os.getenv("IMAGE_TORCH_MODEL_NAME", "vit_base_patch16_224")
TORCH_USE_PRETRAINED = os.getenv("IMAGE_TORCH_PRETRAINED", "0") == "1"
_MODEL_RUNTIME_LOCK = threading.RLock()

_KERAS_MODEL = None
_KERAS_ERROR: Optional[str] = None
_KERAS_INPUT_SHAPE: Optional[Tuple[int, int]] = None
_TORCH_MODEL = None
_TORCH_ERROR: Optional[str] = None
_TORCH_MODEL_NAME: Optional[str] = None


def _default_fake_index() -> int:
    override = os.getenv("IMAGE_MODEL_FAKE_INDEX")
    if override is not None and override != "":
        return int(override)
    return _fake_index_for_path(MODEL_PATH)


def _fake_index_for_path(model_path: Path) -> int:
    # `deepfake_cnn.keras` appears to use output order [fake, real].
    if model_path.name in {"deepfake_cnn.keras", "deepfake.keras"}:
        return 0
    return 1


MODEL_FAKE_INDEX = _default_fake_index()


def _runtime_defaults_for_path(model_path: Optional[Path]) -> dict:
    image_size_override = os.getenv("IMAGE_MODEL_IMAGE_SIZE")
    fake_index_override = os.getenv("IMAGE_MODEL_FAKE_INDEX")
    return {
        "path": model_path,
        "image_size": int(image_size_override) if image_size_override else (224 if model_path is None or model_path.suffix.lower() == ".keras" else 256),
        "preprocess": os.getenv("IMAGE_MODEL_PREPROCESS", "rescale").lower(),
        "fake_index": int(fake_index_override) if fake_index_override not in (None, "") else (_fake_index_for_path(model_path) if model_path is not None else 1),
        "pipeline_mode": PIPELINE_MODE,
        "reference_impl": MODEL_REFERENCE_IMPL,
        "model_name": TORCH_MODEL_NAME,
        "pretrained_weights": TORCH_USE_PRETRAINED,
    }


def _snapshot_runtime() -> dict:
    return {
        "MODEL_PATH": MODEL_PATH,
        "MODEL_IMAGE_SIZE": MODEL_IMAGE_SIZE,
        "MODEL_PREPROCESS": MODEL_PREPROCESS,
        "MODEL_FAKE_INDEX": MODEL_FAKE_INDEX,
        "PIPELINE_MODE": PIPELINE_MODE,
        "MODEL_REFERENCE_IMPL": MODEL_REFERENCE_IMPL,
        "TORCH_MODEL_NAME": TORCH_MODEL_NAME,
        "TORCH_USE_PRETRAINED": TORCH_USE_PRETRAINED,
        "_KERAS_MODEL": _KERAS_MODEL,
        "_KERAS_ERROR": _KERAS_ERROR,
        "_KERAS_INPUT_SHAPE": _KERAS_INPUT_SHAPE,
        "_TORCH_MODEL": _TORCH_MODEL,
        "_TORCH_ERROR": _TORCH_ERROR,
        "_TORCH_MODEL_NAME": _TORCH_MODEL_NAME,
    }


def _apply_runtime(model_config: Optional[dict]) -> None:
    global MODEL_PATH, MODEL_IMAGE_SIZE, MODEL_PREPROCESS, MODEL_FAKE_INDEX, PIPELINE_MODE
    global MODEL_REFERENCE_IMPL, TORCH_MODEL_NAME, TORCH_USE_PRETRAINED
    global _KERAS_MODEL, _KERAS_ERROR, _KERAS_INPUT_SHAPE
    global _TORCH_MODEL, _TORCH_ERROR, _TORCH_MODEL_NAME

    config = model_config or {}
    if "path" in config:
        model_path = Path(config["path"]) if config["path"] else None
    else:
        model_path = MODEL_PATH
    runtime = _runtime_defaults_for_path(model_path)
    runtime.update({k: v for k, v in config.items() if v is not None})

    MODEL_PATH = Path(runtime["path"]) if runtime.get("path") else None
    MODEL_IMAGE_SIZE = int(runtime["image_size"])
    MODEL_PREPROCESS = str(runtime["preprocess"]).lower()
    MODEL_FAKE_INDEX = int(runtime["fake_index"])
    PIPELINE_MODE = str(runtime.get("pipeline_mode") or PIPELINE_MODE).lower()
    MODEL_REFERENCE_IMPL = str(runtime.get("reference_impl") or MODEL_REFERENCE_IMPL).lower()
    TORCH_MODEL_NAME = str(runtime.get("model_name") or TORCH_MODEL_NAME)
    TORCH_USE_PRETRAINED = bool(runtime.get("pretrained_weights", TORCH_USE_PRETRAINED))
    _KERAS_MODEL = None
    _KERAS_ERROR = None
    _KERAS_INPUT_SHAPE = None
    _TORCH_MODEL = None
    _TORCH_ERROR = None
    _TORCH_MODEL_NAME = None


def _restore_runtime(snapshot: dict) -> None:
    global MODEL_PATH, MODEL_IMAGE_SIZE, MODEL_PREPROCESS, MODEL_FAKE_INDEX, PIPELINE_MODE
    global MODEL_REFERENCE_IMPL, TORCH_MODEL_NAME, TORCH_USE_PRETRAINED
    global _KERAS_MODEL, _KERAS_ERROR, _KERAS_INPUT_SHAPE
    global _TORCH_MODEL, _TORCH_ERROR, _TORCH_MODEL_NAME

    MODEL_PATH = snapshot["MODEL_PATH"]
    MODEL_IMAGE_SIZE = snapshot["MODEL_IMAGE_SIZE"]
    MODEL_PREPROCESS = snapshot["MODEL_PREPROCESS"]
    MODEL_FAKE_INDEX = snapshot["MODEL_FAKE_INDEX"]
    PIPELINE_MODE = snapshot["PIPELINE_MODE"]
    MODEL_REFERENCE_IMPL = snapshot["MODEL_REFERENCE_IMPL"]
    TORCH_MODEL_NAME = snapshot["TORCH_MODEL_NAME"]
    TORCH_USE_PRETRAINED = snapshot["TORCH_USE_PRETRAINED"]
    _KERAS_MODEL = snapshot["_KERAS_MODEL"]
    _KERAS_ERROR = snapshot["_KERAS_ERROR"]
    _KERAS_INPUT_SHAPE = snapshot["_KERAS_INPUT_SHAPE"]
    _TORCH_MODEL = snapshot["_TORCH_MODEL"]
    _TORCH_ERROR = snapshot["_TORCH_ERROR"]
    _TORCH_MODEL_NAME = snapshot["_TORCH_MODEL_NAME"]


def error_level_analysis(image: Image.Image, quality: int = 90) -> dict:
    """
    ELA: re-save at lower quality and compare.
    Edited regions show higher error levels due to compression inconsistency.
    """
    original = image.convert("RGB")

    # Re-save at given quality
    buffer = io.BytesIO()
    original.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")

    # Compute difference
    diff = ImageChops.difference(original, resaved)
    extrema = diff.getextrema()

    # Scale for visibility
    scale = 255.0 / max(max(e) for e in extrema) if max(max(e) for e in extrema) > 0 else 1
    ela_image = diff.point(lambda px: min(int(px * scale), 255))

    # Compute mean error per pixel
    diff_arr = np.array(diff, dtype=np.float32)
    mean_error = float(np.mean(diff_arr))
    max_error = float(np.max(diff_arr))

    # High ELA means more manipulation likelihood
    ela_score = min(mean_error / 15.0, 1.0)

    return {
        "ela_score": ela_score,
        "mean_error": round(mean_error, 3),
        "max_error": round(max_error, 3),
        "ela_image": ela_image,
    }


def _load_keras_model():
    global _KERAS_MODEL, _KERAS_ERROR, _KERAS_INPUT_SHAPE

    if _KERAS_MODEL is not None:
        return _KERAS_MODEL, None
    if _KERAS_ERROR:
        return None, _KERAS_ERROR
    if MODEL_PATH is None:
        _KERAS_ERROR = "No Keras image model configured."
        return None, _KERAS_ERROR
    if not MODEL_PATH.exists():
        _KERAS_ERROR = f"Model file not found at {MODEL_PATH}"
        return None, _KERAS_ERROR

    try:
        model = _load_model_from_path(MODEL_PATH)
        _KERAS_MODEL = model

        shape = model.input_shape
        if isinstance(shape, list):
            shape = shape[0]
        if shape is not None and len(shape) >= 4:
            _KERAS_INPUT_SHAPE = (int(shape[1]), int(shape[2]))
        else:
            _KERAS_INPUT_SHAPE = (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)
        return _KERAS_MODEL, None
    except Exception as exc:
        # Some `.keras` archives serialize InputLayer with `batch_shape`,
        # which the current local loader rejects. Patch the archive config
        # in a temp copy and retry.
        if MODEL_PATH.suffix.lower() == ".keras":
            try:
                model = _load_patched_keras_archive()
                _KERAS_MODEL = model
                shape = model.input_shape
                if isinstance(shape, list):
                    shape = shape[0]
                if shape is not None and len(shape) >= 4:
                    _KERAS_INPUT_SHAPE = (int(shape[1]), int(shape[2]))
                else:
                    _KERAS_INPUT_SHAPE = (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)
                return _KERAS_MODEL, None
            except Exception as patched_exc:
                _KERAS_ERROR = str(patched_exc)
                return None, _KERAS_ERROR

        _KERAS_ERROR = str(exc)
        return None, _KERAS_ERROR


def _load_model_from_path(model_path: Path):
    if model_path.suffix.lower() == ".keras":
        try:
            import keras

            return keras.models.load_model(str(model_path), compile=False)
        except Exception:
            pass

    import tensorflow as tf

    return tf.keras.models.load_model(str(model_path), compile=False)


def _load_patched_keras_archive():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        with zipfile.ZipFile(MODEL_PATH) as archive:
            archive.extractall(tmp_root)

        config_path = tmp_root / "config.json"
        config = json.loads(config_path.read_text())
        layers = config.get("config", {}).get("layers", [])
        for layer in layers:
            if layer.get("class_name") != "InputLayer":
                continue
            layer_config = layer.get("config", {})
            if "batch_shape" in layer_config and "batch_input_shape" not in layer_config:
                layer_config["batch_input_shape"] = layer_config.pop("batch_shape")

        config_path.write_text(json.dumps(config))
        patched_path = tmp_root / "patched.keras"
        with zipfile.ZipFile(patched_path, "w") as archive:
            for name in ("metadata.json", "config.json", "model.weights.h5"):
                archive.write(tmp_root / name, arcname=name)

        return _load_model_from_path(patched_path)


def _keras_preprocess(batch: np.ndarray) -> np.ndarray:
    if MODEL_PREPROCESS == "rescale":
        return batch / 255.0
    if MODEL_PREPROCESS == "densenet":
        from tensorflow.keras.applications.densenet import preprocess_input

        return preprocess_input(batch)
    if MODEL_PREPROCESS == "resnet":
        from tensorflow.keras.applications.resnet import preprocess_input

        return preprocess_input(batch)
    return batch


def _hf_cache_has_weights(repo_id: str, candidate_filenames: list[str]) -> bool:
    cache_root = Path(os.getenv("HF_HUB_CACHE", str(Path.home() / ".cache" / "huggingface" / "hub")))
    repo_dir = cache_root / f"models--{repo_id.replace('/', '--')}"
    if not repo_dir.exists():
        return False
    for filename in candidate_filenames:
        if filename and any(repo_dir.glob(f"**/{filename}")):
            return True
    return False


def _create_pretrained_timm_model(model_name: str):
    import timm

    pretrained_cfg = timm.get_pretrained_cfg(model_name)
    repo_id = getattr(pretrained_cfg, "hf_hub_id", None)
    hf_filename = getattr(pretrained_cfg, "hf_hub_filename", None)
    if repo_id:
        candidate_filenames = [hf_filename] if hf_filename else []
        candidate_filenames.extend(["model.safetensors", "pytorch_model.bin"])
        if not _hf_cache_has_weights(repo_id, candidate_filenames):
            raise RuntimeError(
                f"Pretrained weights for {model_name} are not cached locally. "
                "Download them once in an environment with internet access, then rerun."
            )

    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    previous_progress = os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        return timm.create_model(model_name, pretrained=True)
    finally:
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
        if previous_progress is None:
            os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
        else:
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = previous_progress


def _torch_load_checkpoint(model_path: Path):
    import torch

    kwargs = {"map_location": "cpu"}
    try:
        if "weights_only" in inspect.signature(torch.load).parameters:
            kwargs["weights_only"] = False
    except (TypeError, ValueError):
        pass
    return torch.load(str(model_path), **kwargs)


def _load_torch_model():
    global _TORCH_MODEL, _TORCH_ERROR, _TORCH_MODEL_NAME

    if _TORCH_MODEL is not None:
        return _TORCH_MODEL, None
    if _TORCH_ERROR:
        return None, _TORCH_ERROR
    if MODEL_PATH is None and TORCH_USE_PRETRAINED:
        try:
            _TORCH_MODEL = _create_pretrained_timm_model(TORCH_MODEL_NAME)
            _TORCH_MODEL.eval()
            _TORCH_MODEL_NAME = TORCH_MODEL_NAME
            return _TORCH_MODEL, None
        except Exception as exc:
            _TORCH_ERROR = str(exc)
            return None, _TORCH_ERROR

    if MODEL_PATH is None or not MODEL_PATH.exists():
        _TORCH_ERROR = f"Model file not found at {MODEL_PATH}"
        return None, _TORCH_ERROR

    try:
        import timm

        checkpoint = _torch_load_checkpoint(MODEL_PATH)
        state_dict = checkpoint.get("state_dict") if isinstance(checkpoint, dict) and "state_dict" in checkpoint else checkpoint
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
        if not isinstance(state_dict, dict):
            raise ValueError("Unsupported transformer checkpoint format.")

        cleaned = {}
        for key, value in state_dict.items():
            cleaned[key[7:] if key.startswith("module.") else key] = value

        candidates = [
            "deit_small_patch16_224",
            "deit_base_patch16_224",
            "vit_base_patch16_224",
            "vit_small_patch16_224",
        ]
        best = None
        best_score = None
        for candidate in candidates:
            try:
                model = timm.create_model(candidate, pretrained=False, num_classes=2)
                missing, unexpected = model.load_state_dict(cleaned, strict=False)
                score = len(missing) + len(unexpected)
                if best_score is None or score < best_score:
                    best = (model, candidate)
                    best_score = score
                    if score == 0:
                        break
            except Exception:
                continue

        if best is None:
            raise ValueError("No compatible ViT/DeiT architecture matched the checkpoint.")

        _TORCH_MODEL, _TORCH_MODEL_NAME = best
        _TORCH_MODEL.eval()
        return _TORCH_MODEL, None
    except Exception as exc:
        _TORCH_ERROR = str(exc)
        return None, _TORCH_ERROR


def predict_image_transformer_model(image: Image.Image) -> dict:
    model, err = _load_torch_model()
    if err:
        return {
            "available": False,
            "score": None,
            "probabilities": None,
            "version": "unavailable",
            "error": err,
        }

    try:
        import torch
        from torchvision import transforms

        transform = transforms.Compose([
            transforms.Resize((MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        batch = transform(image.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            preds = model(batch)
        if isinstance(preds, (tuple, list)):
            preds = preds[0]
        preds = torch.as_tensor(preds)
        if preds.ndim == 1:
            preds = preds.unsqueeze(0)

        if TORCH_USE_PRETRAINED and preds.shape[1] > 2:
            probs = torch.softmax(preds, dim=-1)
            top_values, _ = torch.topk(probs, k=min(2, probs.shape[1]), dim=-1)
            top1 = float(top_values[0, 0].item())
            top2 = float(top_values[0, 1].item()) if top_values.shape[1] > 1 else 0.0
            entropy = float((-(probs * torch.log(probs.clamp_min(1e-9))).sum(dim=-1) / np.log(probs.shape[1])).item())
            fake_score = float(np.clip((0.65 * entropy) + (0.20 * (1.0 - top1)) + (0.15 * (1.0 - max(top1 - top2, 0.0))), 0.0, 1.0))
            probabilities = [round(1.0 - fake_score, 6), round(fake_score, 6)]
            version = f"torch-pretrained:{TORCH_MODEL_NAME}"
        elif preds.shape[1] == 1:
            fake_score = float(torch.sigmoid(preds)[0, 0].item())
            probabilities = [round(1.0 - fake_score, 6), round(fake_score, 6)]
            version = f"torch:{MODEL_PATH.name}:{_TORCH_MODEL_NAME}" if MODEL_PATH else f"torch:{_TORCH_MODEL_NAME}"
        else:
            probs = torch.softmax(preds, dim=-1)
            fake_index = MODEL_FAKE_INDEX if 0 <= MODEL_FAKE_INDEX < probs.shape[1] else probs.shape[1] - 1
            fake_score = float(probs[0, fake_index].item())
            probabilities = [round(float(p), 6) for p in probs[0].tolist()]
            version = f"torch:{MODEL_PATH.name}:{_TORCH_MODEL_NAME}" if MODEL_PATH else f"torch:{_TORCH_MODEL_NAME}"

        return {
            "available": True,
            "score": round(min(max(fake_score, 0.0), 1.0), 4),
            "probabilities": probabilities,
            "version": version,
            "fake_index": MODEL_FAKE_INDEX,
            "label_map": {"fake": MODEL_FAKE_INDEX},
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "score": None,
            "probabilities": None,
            "version": f"torch:{MODEL_PATH.name}",
            "fake_index": MODEL_FAKE_INDEX,
            "label_map": {"fake": MODEL_FAKE_INDEX},
            "error": str(exc),
        }


def predict_image_model(image: Image.Image) -> dict:
    if TORCH_USE_PRETRAINED or (MODEL_PATH is not None and MODEL_PATH.suffix.lower() in {".pt", ".pth"}):
        return predict_image_transformer_model(image)

    model, err = _load_keras_model()
    if err:
        return {
            "available": False,
            "score": None,
            "probabilities": None,
            "version": "unavailable",
            "error": err,
        }

    try:
        width, height = _KERAS_INPUT_SHAPE or (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)
        rgb = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        batch = np.asarray(rgb, dtype=np.float32)[None, ...]
        batch = _keras_preprocess(batch)
        preds = np.asarray(model.predict(batch, verbose=0))

        if preds.ndim == 2 and preds.shape[1] == 1:
            fake_score = float(preds.reshape(-1)[0])
            probabilities = [round(1.0 - fake_score, 6), round(fake_score, 6)]
        elif preds.ndim == 2 and preds.shape[1] >= 2:
            probs = preds
            if probs.max() > 1.0 or probs.min() < 0.0:
                exps = np.exp(probs - np.max(probs, axis=1, keepdims=True))
                probs = exps / np.sum(exps, axis=1, keepdims=True)
            fake_index = MODEL_FAKE_INDEX
            if fake_index < 0 or fake_index >= probs.shape[1]:
                fake_index = probs.shape[1] - 1
            fake_score = float(probs[0, fake_index])
            probabilities = [round(float(p), 6) for p in probs[0].tolist()]
        else:
            raise ValueError(f"Unsupported prediction shape: {preds.shape}")

        return {
            "available": True,
            "score": round(min(max(fake_score, 0.0), 1.0), 4),
            "probabilities": probabilities,
            "version": f"keras:{MODEL_PATH.name}",
            "fake_index": fake_index if preds.ndim == 2 and preds.shape[1] >= 2 else MODEL_FAKE_INDEX,
            "label_map": {
                "fake": fake_index if preds.ndim == 2 and preds.shape[1] >= 2 else MODEL_FAKE_INDEX,
                "real": 0 if (preds.ndim == 2 and preds.shape[1] == 1) else (
                    1 - fake_index if preds.ndim == 2 and preds.shape[1] == 2 and fake_index in (0, 1) else None
                ),
            },
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "score": None,
            "probabilities": None,
            "version": f"keras:{MODEL_PATH.name}",
            "fake_index": MODEL_FAKE_INDEX,
            "label_map": {"fake": MODEL_FAKE_INDEX},
            "error": str(exc),
        }


def frequency_analysis(image: Image.Image) -> dict:
    """
    FFT-based frequency analysis.
    GANs produce characteristic frequency domain artifacts.
    """
    gray = np.array(image.convert("L"), dtype=np.float32)
    f_transform = fft2(gray)
    f_shift = fftshift(f_transform)
    magnitude = np.log1p(np.abs(f_shift))

    # Analyze spectral distribution
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2

    # Radial energy distribution
    low_freq = float(np.mean(magnitude[cy - 10:cy + 10, cx - 10:cx + 10]))
    high_freq_region = np.concatenate([
        magnitude[:20, :].flatten(),
        magnitude[-20:, :].flatten(),
        magnitude[:, :20].flatten(),
        magnitude[:, -20:].flatten(),
    ])
    high_freq = float(np.mean(high_freq_region))

    # Treat only clear deviations from a broad normal band as suspicious.
    ratio = high_freq / (low_freq + 1e-6)
    normal_low = 0.35
    normal_high = 0.72
    if ratio < normal_low:
        deviation = (normal_low - ratio) / normal_low
    elif ratio > normal_high:
        deviation = (ratio - normal_high) / max(1e-6, 1.0 - normal_high)
    else:
        deviation = 0.0
    freq_anomaly_score = min(max(deviation * 1.8, 0.0), 1.0)

    return {
        "freq_anomaly_score": freq_anomaly_score,
        "low_freq_energy": round(low_freq, 3),
        "high_freq_energy": round(high_freq, 3),
        "spectral_ratio": round(ratio, 4),
    }


def color_channel_analysis(image: Image.Image) -> dict:
    """
    Analyze RGB channel statistics for inconsistencies.
    Deepfakes may show unusual color distributions.
    """
    arr = np.array(image.convert("RGB"), dtype=np.float32)
    channels = {"red": arr[:, :, 0], "green": arr[:, :, 1], "blue": arr[:, :, 2]}

    stats = {}
    means = []
    stds = []
    for name, ch in channels.items():
        m = float(np.mean(ch))
        s = float(np.std(ch))
        stats[name] = {"mean": round(m, 2), "std": round(s, 2)}
        means.append(m)
        stds.append(s)

    # Cross-channel variance (higher = more suspicious)
    mean_variance = float(np.var(means))
    std_variance = float(np.var(stds))
    color_score = min((mean_variance / 500.0 + std_variance / 200.0), 1.0)

    return {
        "color_score": color_score,
        "channel_stats": stats,
        "mean_variance": round(mean_variance, 3),
        "std_variance": round(std_variance, 3),
    }


def generate_heatmap(image: Image.Image) -> Image.Image:
    """Generate an overlay-style forensic heatmap over the original image."""
    ela_result = error_level_analysis(image)
    ela_img = ela_result["ela_image"].convert("L").filter(ImageFilter.GaussianBlur(radius=3))
    arr = np.array(ela_img, dtype=np.float32)

    if arr.max() <= 0:
        return image.convert("RGB")

    lo = float(np.percentile(arr, 70))
    hi = float(np.percentile(arr, 99.5))
    if hi <= lo:
        lo = float(arr.min())
        hi = float(arr.max())

    normalized = np.clip((arr - lo) / (hi - lo + 1e-6), 0.0, 1.0)
    normalized = np.power(normalized, 1.6)

    alpha = np.clip((normalized - 0.08) / 0.92, 0.0, 1.0) * 0.82

    base = np.array(image.convert("RGB"), dtype=np.float32)
    heat = np.zeros_like(base)
    heat[:, :, 0] = 255.0
    heat[:, :, 1] = np.clip(normalized * 235.0, 0.0, 235.0)
    heat[:, :, 2] = np.clip((1.0 - normalized) * 40.0, 0.0, 40.0)

    overlay = (base * (1.0 - alpha[..., None])) + (heat * alpha[..., None])
    return Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))


def detect_image(image_path: str, model_config: Optional[dict] = None) -> dict:
    """Full image detection pipeline."""
    with _MODEL_RUNTIME_LOCK:
        snapshot = _snapshot_runtime()
        try:
            _apply_runtime(model_config)
            image = Image.open(image_path)

            ela = error_level_analysis(image)
            freq = frequency_analysis(image)
            color = color_channel_analysis(image)
            model = predict_image_model(image)

            heuristic_score = (
                ela["ela_score"] * 0.25
                + freq["freq_anomaly_score"] * 0.20
                + color["color_score"] * 0.55
            )

            if PIPELINE_MODE == "frequency_only":
                overall = round(min(max(freq["freq_anomaly_score"], 0), 1), 4)
                model_version = "frequency-domain"
            elif model["available"] and model["score"] is not None:
                model_confidence = min(max(abs(float(model["score"]) - 0.5) * 2.0, 0.0), 1.0)
                effective_model_weight = MODEL_WEIGHT * max(0.15, model_confidence)
                if str(model.get("version", "")).startswith("torch-pretrained:"):
                    effective_model_weight = min(effective_model_weight, 0.2)
                effective_heuristic_weight = max(0.0, 1.0 - effective_model_weight)
                overall = (heuristic_score * effective_heuristic_weight) + (model["score"] * effective_model_weight)
                model_version = model["version"]
            else:
                overall = heuristic_score
                model_version = "heuristics-only"

            overall = round(min(max(overall, 0), 1), 4)

            if overall > 0.62:
                verdict = "MANIPULATED"
            elif overall > 0.24:
                verdict = "SUSPICIOUS"
            else:
                verdict = "AUTHENTIC"

            evidence = []
            if ela["ela_score"] > 0.3:
                evidence.append({
                    "type": "ela",
                    "title": "Error Level Analysis Anomaly",
                    "description": f"ELA detected compression inconsistencies (score: {ela['ela_score']:.2f}). "
                                 f"Mean error: {ela['mean_error']}, max error: {ela['max_error']}.",
                    "severity": "high" if ela["ela_score"] > 0.6 else "medium",
                })
            if freq["freq_anomaly_score"] > 0.3:
                evidence.append({
                    "type": "frequency",
                    "title": "Frequency Domain Anomaly",
                    "description": f"Abnormal spectral distribution detected (score: {freq['freq_anomaly_score']:.2f}). "
                                 f"Spectral ratio: {freq['spectral_ratio']}. Possible GAN artifacts.",
                    "severity": "high" if freq["freq_anomaly_score"] > 0.6 else "medium",
                })
            if color["color_score"] > 0.3:
                evidence.append({
                    "type": "color",
                    "title": "Color Channel Inconsistency",
                    "description": f"Unusual color distribution detected (score: {color['color_score']:.2f}). "
                                 f"Channel variance: {color['mean_variance']}.",
                    "severity": "medium",
                })
            if PIPELINE_MODE == "frequency_only":
                evidence.append({
                    "type": "frequency",
                    "title": "Frequency Domain Model",
                    "description": (
                        f"Frequency-only image analysis reported a manipulation score of {freq['freq_anomaly_score']:.2f}. "
                        f"Spectral ratio: {freq['spectral_ratio']}."
                    ),
                    "severity": "high" if freq["freq_anomaly_score"] > 0.65 else "medium" if freq["freq_anomaly_score"] > 0.35 else "info",
                })
            elif model["available"] and model["score"] is not None:
                is_pretrained_transformer = str(model.get("version", "")).startswith("torch-pretrained:")
                evidence.append({
                    "type": "model",
                    "title": "Transformer Image Signal" if is_pretrained_transformer else "CNN Image Manipulation Score",
                    "description": (
                        f"The image model estimated a manipulation probability of {model['score']:.2f}. "
                        f"Class mapping uses fake index {model.get('fake_index')}. "
                        f"Low-confidence model outputs are down-weighted during fusion."
                    ),
                    "severity": "high" if model["score"] > 0.65 else "medium" if model["score"] > 0.35 else "info",
                })
                if is_pretrained_transformer:
                    evidence.append({
                        "type": "transformer_status",
                        "title": "Pretrained ViT/DeiT Signal",
                        "description": (
                            "This score comes from an ImageNet-pretrained transformer and is treated as an experimental auxiliary signal, "
                            "not a deepfake-trained classifier."
                        ),
                        "severity": "info",
                    })
            elif model["error"]:
                evidence.append({
                    "type": "model_status",
                    "title": "CNN Model Unavailable",
                    "description": f"Image model inference was skipped because the Keras model could not be loaded: {model['error']}",
                    "severity": "info",
                })

            heatmap = generate_heatmap(image)

            return {
                "overall_score": overall,
                "heuristic_score": round(heuristic_score, 4),
                "verdict": verdict,
                "ela": {k: v for k, v in ela.items() if k != "ela_image"},
                "frequency": freq,
                "color": color,
                "model": model,
                "model_version": model_version,
                "evidence": evidence,
                "heatmap": heatmap,
            }
        finally:
            _restore_runtime(snapshot)
