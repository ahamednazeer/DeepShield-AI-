"""
Image Deepfake Detection Pipeline
Uses a CNN classifier plus heuristic forensic signals
(ELA, FFT, and color statistics).
"""

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageFilter
from scipy.fft import fft2, fftshift

# Support loading older checked-in .h5 models.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

MODEL_PATH = Path(os.getenv("IMAGE_MODEL_PATH", str(Path(__file__).resolve().parent.parent / "models" / "deepfake_cnn.keras")))
MODEL_IMAGE_SIZE = int(os.getenv("IMAGE_MODEL_IMAGE_SIZE", "256"))
MODEL_WEIGHT = float(os.getenv("IMAGE_MODEL_WEIGHT", "0.6"))
HEURISTIC_WEIGHT = float(os.getenv("IMAGE_HEURISTIC_WEIGHT", "0.4"))
MODEL_PREPROCESS = os.getenv("IMAGE_MODEL_PREPROCESS", "rescale").lower()

_KERAS_MODEL = None
_KERAS_ERROR: Optional[str] = None
_KERAS_INPUT_SHAPE: Optional[Tuple[int, int]] = None


def _default_fake_index() -> int:
    override = os.getenv("IMAGE_MODEL_FAKE_INDEX")
    if override is not None and override != "":
        return int(override)
    # `deepfake_cnn.keras` appears to use output order [fake, real].
    if MODEL_PATH.name == "deepfake_cnn.keras":
        return 0
    return 1


MODEL_FAKE_INDEX = _default_fake_index()


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


def predict_image_model(image: Image.Image) -> dict:
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

    # GAN images tend to have abnormal high-frequency patterns
    ratio = high_freq / (low_freq + 1e-6)
    freq_anomaly_score = min(ratio * 2.5, 1.0)

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


def detect_image(image_path: str) -> dict:
    """Full image detection pipeline."""
    image = Image.open(image_path)

    ela = error_level_analysis(image)
    freq = frequency_analysis(image)
    color = color_channel_analysis(image)
    model = predict_image_model(image)

    heuristic_score = (
        ela["ela_score"] * 0.4
        + freq["freq_anomaly_score"] * 0.35
        + color["color_score"] * 0.25
    )

    if model["available"] and model["score"] is not None:
        overall = (heuristic_score * HEURISTIC_WEIGHT) + (model["score"] * MODEL_WEIGHT)
        model_version = model["version"]
    else:
        overall = heuristic_score
        model_version = "heuristics-only"

    overall = round(min(max(overall, 0), 1), 4)

    # Determine verdict
    if overall > 0.65:
        verdict = "MANIPULATED"
    elif overall > 0.35:
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
    if model["available"] and model["score"] is not None:
        evidence.append({
            "type": "model",
            "title": "CNN Image Manipulation Score",
            "description": (
                f"The image CNN model estimated a manipulation probability of {model['score']:.2f}. "
                f"Class mapping uses fake index {model.get('fake_index')}."
            ),
            "severity": "high" if model["score"] > 0.65 else "medium" if model["score"] > 0.35 else "info",
        })
    elif model["error"]:
        evidence.append({
            "type": "model_status",
            "title": "CNN Model Unavailable",
            "description": f"Image model inference was skipped because the Keras model could not be loaded: {model['error']}",
            "severity": "info",
        })

    # Generate heatmap
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
