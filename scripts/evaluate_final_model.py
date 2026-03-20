#!/usr/bin/env python3
"""
Evaluate backend/models/final_model.keras against labeled real/fake image folders.

Examples:
    python3 scripts/evaluate_final_model.py \
        --dataset-root /path/to/dataset

    python3 scripts/evaluate_final_model.py \
        --real-dir /path/to/real \
        --fake-dir /path/to/fake \
        --output-json /tmp/final_model_eval.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

try:
    RESAMPLING = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLING = Image.LANCZOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate final_model.keras on separate real/fake image folders."
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path("backend/models/final_model.keras"),
        help="Path to the Keras model to evaluate.",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="Dataset root containing `real/` and `fake/` directories.",
    )
    parser.add_argument(
        "--real-dir",
        type=Path,
        default=None,
        help="Directory of real images.",
    )
    parser.add_argument(
        "--fake-dir",
        type=Path,
        default=None,
        help="Directory of fake images.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Fake-probability threshold for predicted label.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Inference batch size.",
    )
    parser.add_argument(
        "--limit-per-class",
        type=int,
        default=None,
        help="Optional cap on images loaded from each class directory.",
    )
    parser.add_argument(
        "--fake-index",
        type=int,
        default=1,
        help="Fake class index when the model returns multiple probabilities.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write full evaluation output as JSON.",
    )
    parser.add_argument(
        "--preprocess",
        choices=("auto", "xception", "vgg16", "mobilenetv2", "efficientnetb0", "rescale", "none"),
        default="auto",
        help="Loader-side preprocess function name for models saved with Lambda(preprocess_input).",
    )
    parser.add_argument(
        "--input-preprocess",
        choices=("none", "xception", "vgg16", "mobilenetv2", "efficientnetb0", "rescale"),
        default="none",
        help="Optional preprocess applied to image batches before model.predict().",
    )
    return parser.parse_args()


def resolve_dataset_dirs(args: argparse.Namespace) -> tuple[Path, Path]:
    real_dir = args.real_dir
    fake_dir = args.fake_dir

    if args.dataset_root is not None:
        real_dir = args.dataset_root / "real"
        fake_dir = args.dataset_root / "fake"

    if real_dir is None or fake_dir is None:
        raise ValueError("Provide either --dataset-root or both --real-dir and --fake-dir.")

    if not real_dir.exists():
        raise FileNotFoundError(f"Real image directory not found: {real_dir}")
    if not fake_dir.exists():
        raise FileNotFoundError(f"Fake image directory not found: {fake_dir}")

    return real_dir, fake_dir


def collect_images(directory: Path, limit: int | None) -> list[Path]:
    paths = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if limit is not None:
        paths = paths[:limit]
    return paths


def _patch_keras_config(payload: object) -> None:
    if isinstance(payload, dict):
        if payload.get("class_name") == "InputLayer":
            layer_config = payload.get("config", {})
            if "batch_shape" in layer_config and "batch_input_shape" not in layer_config:
                layer_config["batch_input_shape"] = layer_config.pop("batch_shape")
        layer_config = payload.get("config")
        if isinstance(layer_config, dict):
            layer_config.pop("quantization_config", None)
        for value in payload.values():
            _patch_keras_config(value)
        return

    if isinstance(payload, list):
        for item in payload:
            _patch_keras_config(item)


def infer_preprocess_name(model_name: str, override: str) -> str:
    if override != "auto":
        return override

    lower_name = model_name.lower()
    if "xception" in lower_name:
        return "xception"
    if "vgg16" in lower_name:
        return "vgg16"
    if "mobilenetv2" in lower_name:
        return "mobilenetv2"
    if "efficientnetb0" in lower_name:
        return "efficientnetb0"
    return "none"


def get_preprocess_function(name: str) -> Callable[[np.ndarray], np.ndarray]:
    if name == "rescale":
        return lambda batch: batch / 255.0
    if name == "xception":
        from tensorflow.keras.applications.xception import preprocess_input

        return preprocess_input
    if name == "vgg16":
        from tensorflow.keras.applications.vgg16 import preprocess_input

        return preprocess_input
    if name == "mobilenetv2":
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

        return preprocess_input
    if name == "efficientnetb0":
        from tensorflow.keras.applications.efficientnet import preprocess_input

        return preprocess_input
    return lambda batch: batch


def load_model_with_metadata(
    model_path: Path,
    preprocess_name: str,
):
    import tensorflow as tf

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    if model_path.suffix.lower() != ".keras":
        model = tf.keras.models.load_model(str(model_path), compile=False)
        shape = model.input_shape[0] if isinstance(model.input_shape, list) else model.input_shape
        return model, {
            "model_name": getattr(model, "name", model_path.stem),
            "input_shape": list(shape) if shape is not None else None,
            "preprocess": preprocess_name,
            "patched_archive": False,
        }

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        with zipfile.ZipFile(model_path) as archive:
            archive.extractall(tmp_root)

        config_path = tmp_root / "config.json"
        config = json.loads(config_path.read_text())
        _patch_keras_config(config)
        config_path.write_text(json.dumps(config))

        model_name = str(config.get("config", {}).get("name", model_path.stem))
        effective_preprocess = infer_preprocess_name(model_name, preprocess_name)
        preprocess_fn = get_preprocess_function(effective_preprocess)

        patched_path = tmp_root / "patched.keras"
        with zipfile.ZipFile(patched_path, "w") as archive:
            for name in ("metadata.json", "config.json", "model.weights.h5"):
                archive.write(tmp_root / name, arcname=name)

        model = tf.keras.models.load_model(
            str(patched_path),
            compile=False,
            safe_mode=False,
            custom_objects={"preprocess_input": preprocess_fn},
        )
        shape = model.input_shape[0] if isinstance(model.input_shape, list) else model.input_shape
        return model, {
            "model_name": model_name,
            "input_shape": list(shape) if shape is not None else None,
            "preprocess": effective_preprocess,
            "patched_archive": True,
        }


def load_batch(paths: Iterable[Path], width: int, height: int) -> np.ndarray:
    images = []
    for path in paths:
        image = Image.open(path).convert("RGB").resize((width, height), RESAMPLING)
        images.append(np.asarray(image, dtype=np.float32))
    return np.stack(images, axis=0)


def extract_fake_scores(predictions: np.ndarray, fake_index: int) -> list[float]:
    preds = np.asarray(predictions)
    if preds.ndim == 2 and preds.shape[1] == 1:
        return [float(value) for value in preds.reshape(-1)]

    if preds.ndim == 2 and preds.shape[1] >= 2:
        index = max(0, min(fake_index, preds.shape[1] - 1))
        return [float(value) for value in preds[:, index]]

    raise ValueError(f"Unsupported prediction shape: {preds.shape}")


def binary_auc(y_true: list[int], y_score: list[float]) -> float | None:
    positives = sum(y_true)
    negatives = len(y_true) - positives
    if positives == 0 or negatives == 0:
        return None

    ordered = sorted(enumerate(y_score), key=lambda item: item[1])
    ranks = [0.0] * len(y_score)
    index = 0
    next_rank = 1.0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_rank = (next_rank + (next_rank + (end - index))) / 2.0
        for current in range(index, end + 1):
            ranks[ordered[current][0]] = average_rank
        next_rank += end - index + 1
        index = end + 1

    positive_rank_sum = sum(ranks[i] for i, label in enumerate(y_true) if label == 1)
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def compute_metrics(y_true: list[int], y_pred: list[int], y_score: list[float]) -> dict[str, float | int | None]:
    total = len(y_true)
    tp = sum(1 for actual, pred in zip(y_true, y_pred) if actual == 1 and pred == 1)
    tn = sum(1 for actual, pred in zip(y_true, y_pred) if actual == 0 and pred == 0)
    fp = sum(1 for actual, pred in zip(y_true, y_pred) if actual == 0 and pred == 1)
    fn = sum(1 for actual, pred in zip(y_true, y_pred) if actual == 1 and pred == 0)

    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    auc = binary_auc(y_true, y_score)

    return {
        "samples": total,
        "accuracy": round(accuracy, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "auc": round(auc, 6) if auc is not None else None,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "true_positive": tp,
    }


def evaluate_model(
    model,
    real_images: list[Path],
    fake_images: list[Path],
    width: int,
    height: int,
    batch_size: int,
    threshold: float,
    fake_index: int,
    input_preprocess: Callable[[np.ndarray], np.ndarray] | None = None,
) -> dict[str, object]:
    paths = real_images + fake_images
    labels = [0] * len(real_images) + [1] * len(fake_images)

    scores: list[float] = []
    for start in range(0, len(paths), batch_size):
        batch_paths = paths[start:start + batch_size]
        batch = load_batch(batch_paths, width=width, height=height)
        if input_preprocess is not None:
            batch = input_preprocess(batch)
        predictions = model.predict(batch, verbose=0)
        scores.extend(extract_fake_scores(predictions, fake_index=fake_index))

    predictions = [1 if score >= threshold else 0 for score in scores]
    metrics = compute_metrics(labels, predictions, scores)

    rows = []
    for path, label, score, predicted in zip(paths, labels, scores, predictions):
        rows.append(
            {
                "path": str(path),
                "actual": "fake" if label else "real",
                "predicted": "fake" if predicted else "real",
                "fake_score": round(float(score), 6),
                "correct": label == predicted,
            }
        )

    false_positives = sorted(
        (row for row in rows if row["actual"] == "real" and row["predicted"] == "fake"),
        key=lambda row: row["fake_score"],
        reverse=True,
    )[:5]
    false_negatives = sorted(
        (row for row in rows if row["actual"] == "fake" and row["predicted"] == "real"),
        key=lambda row: row["fake_score"],
    )[:5]

    return {
        "metrics": metrics,
        "threshold": threshold,
        "real_count": len(real_images),
        "fake_count": len(fake_images),
        "false_positives_preview": false_positives,
        "false_negatives_preview": false_negatives,
        "predictions": rows,
    }


def main() -> None:
    args = parse_args()
    real_dir, fake_dir = resolve_dataset_dirs(args)

    real_images = collect_images(real_dir, limit=args.limit_per_class)
    fake_images = collect_images(fake_dir, limit=args.limit_per_class)

    if not real_images:
        raise FileNotFoundError(f"No supported images found in real directory: {real_dir}")
    if not fake_images:
        raise FileNotFoundError(f"No supported images found in fake directory: {fake_dir}")

    model, model_info = load_model_with_metadata(
        model_path=args.model_path,
        preprocess_name=args.preprocess,
    )
    input_preprocess = get_preprocess_function(args.input_preprocess)

    input_shape = model_info.get("input_shape")
    if not input_shape or len(input_shape) < 4:
        raise ValueError(f"Could not determine model input shape: {input_shape}")
    width = int(input_shape[1])
    height = int(input_shape[2])

    evaluation = evaluate_model(
        model=model,
        real_images=real_images,
        fake_images=fake_images,
        width=width,
        height=height,
        batch_size=args.batch_size,
        threshold=args.threshold,
        fake_index=args.fake_index,
        input_preprocess=input_preprocess,
    )

    payload = {
        "model": {
            "path": str(args.model_path),
            **model_info,
            "input_preprocess": args.input_preprocess,
        },
        "dataset": {
            "real_dir": str(real_dir),
            "fake_dir": str(fake_dir),
        },
        **evaluation,
    }

    print(json.dumps(
        {
            "model": payload["model"],
            "dataset": payload["dataset"],
            "threshold": payload["threshold"],
            "metrics": payload["metrics"],
            "false_positives_preview": payload["false_positives_preview"],
            "false_negatives_preview": payload["false_negatives_preview"],
        },
        indent=2,
    ))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote evaluation JSON to {args.output_json}")


if __name__ == "__main__":
    main()
