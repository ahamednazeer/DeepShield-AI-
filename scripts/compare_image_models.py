#!/usr/bin/env python3
"""
Compare backend/models/final_model.keras and backend/models/deepfake_cnn.keras
on the same labeled real/fake image dataset.

Examples:
    python3 scripts/compare_image_models.py --dataset-root /path/to/dataset

    python3 scripts/compare_image_models.py \
        --real-dir /path/to/real \
        --fake-dir /path/to/fake \
        --output-json /tmp/model_compare.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


EVALUATOR_PATH = Path(__file__).with_name("evaluate_final_model.py")


def load_evaluator_module():
    spec = importlib.util.spec_from_file_location("evaluate_final_model", EVALUATOR_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load evaluator module from {EVALUATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare final_model.keras vs deepfake_cnn.keras on the same image dataset."
    )
    parser.add_argument("--dataset-root", type=Path, default=None, help="Dataset root containing real/ and fake/.")
    parser.add_argument("--real-dir", type=Path, default=None, help="Directory containing real images.")
    parser.add_argument("--fake-dir", type=Path, default=None, help="Directory containing fake images.")
    parser.add_argument("--threshold", type=float, default=0.5, help="Fake-probability threshold.")
    parser.add_argument("--batch-size", type=int, default=16, help="Inference batch size.")
    parser.add_argument(
        "--limit-per-class",
        type=int,
        default=None,
        help="Optional cap on images loaded from each class directory.",
    )
    parser.add_argument(
        "--final-model-path",
        type=Path,
        default=Path("backend/models/final_model.keras"),
        help="Path to final_model.keras.",
    )
    parser.add_argument(
        "--cnn-model-path",
        type=Path,
        default=Path("backend/models/deepfake_cnn.keras"),
        help="Path to deepfake_cnn.keras.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the full comparison output as JSON.",
    )
    return parser.parse_args()


def head_to_head_summary(results: dict[str, dict[str, object]]) -> dict[str, object]:
    names = list(results.keys())
    if len(names) != 2:
        return {}

    left_name, right_name = names
    left_predictions = {
        row["path"]: row for row in results[left_name]["predictions"]  # type: ignore[index]
    }
    right_predictions = {
        row["path"]: row for row in results[right_name]["predictions"]  # type: ignore[index]
    }
    shared_paths = sorted(set(left_predictions) & set(right_predictions))

    left_only_correct = []
    right_only_correct = []
    both_correct = 0
    both_wrong = 0

    for path in shared_paths:
        left_row = left_predictions[path]
        right_row = right_predictions[path]
        left_correct = bool(left_row["correct"])
        right_correct = bool(right_row["correct"])

        if left_correct and right_correct:
            both_correct += 1
        elif not left_correct and not right_correct:
            both_wrong += 1
        elif left_correct and not right_correct:
            left_only_correct.append(
                {
                    "path": path,
                    left_name: {
                        "predicted": left_row["predicted"],
                        "fake_score": left_row["fake_score"],
                    },
                    right_name: {
                        "predicted": right_row["predicted"],
                        "fake_score": right_row["fake_score"],
                    },
                }
            )
        elif right_correct and not left_correct:
            right_only_correct.append(
                {
                    "path": path,
                    left_name: {
                        "predicted": left_row["predicted"],
                        "fake_score": left_row["fake_score"],
                    },
                    right_name: {
                        "predicted": right_row["predicted"],
                        "fake_score": right_row["fake_score"],
                    },
                }
            )

    return {
        "shared_samples": len(shared_paths),
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        f"{left_name}_only_correct_count": len(left_only_correct),
        f"{right_name}_only_correct_count": len(right_only_correct),
        f"{left_name}_only_correct_preview": left_only_correct[:5],
        f"{right_name}_only_correct_preview": right_only_correct[:5],
    }


def main() -> None:
    args = parse_args()
    evaluator = load_evaluator_module()

    dataset_args = argparse.Namespace(
        dataset_root=args.dataset_root,
        real_dir=args.real_dir,
        fake_dir=args.fake_dir,
    )
    real_dir, fake_dir = evaluator.resolve_dataset_dirs(dataset_args)
    real_images = evaluator.collect_images(real_dir, args.limit_per_class)
    fake_images = evaluator.collect_images(fake_dir, args.limit_per_class)

    if not real_images:
        raise FileNotFoundError(f"No supported images found in real directory: {real_dir}")
    if not fake_images:
        raise FileNotFoundError(f"No supported images found in fake directory: {fake_dir}")

    model_specs = [
        {
            "name": "final_model",
            "path": args.final_model_path,
            "loader_preprocess": "auto",
            "input_preprocess": "none",
            "fake_index": 1,
        },
        {
            "name": "deepfake_cnn",
            "path": args.cnn_model_path,
            "loader_preprocess": "none",
            "input_preprocess": "rescale",
            "fake_index": 0,
        },
    ]

    results: dict[str, dict[str, object]] = {}
    for spec in model_specs:
        model, model_info = evaluator.load_model_with_metadata(
            model_path=spec["path"],
            preprocess_name=spec["loader_preprocess"],
        )
        input_shape = model_info.get("input_shape")
        if not input_shape or len(input_shape) < 4:
            raise ValueError(f"Could not determine model input shape for {spec['name']}: {input_shape}")

        width = int(input_shape[1])
        height = int(input_shape[2])
        evaluation = evaluator.evaluate_model(
            model=model,
            real_images=real_images,
            fake_images=fake_images,
            width=width,
            height=height,
            batch_size=args.batch_size,
            threshold=args.threshold,
            fake_index=spec["fake_index"],
            input_preprocess=evaluator.get_preprocess_function(spec["input_preprocess"]),
        )
        results[spec["name"]] = {
            "model": {
                "path": str(spec["path"]),
                **model_info,
                "input_preprocess": spec["input_preprocess"],
                "fake_index": spec["fake_index"],
            },
            **evaluation,
        }

    ranking = sorted(
        (
            {
                "name": name,
                "f1": result["metrics"]["f1"],  # type: ignore[index]
                "auc": result["metrics"]["auc"],  # type: ignore[index]
                "accuracy": result["metrics"]["accuracy"],  # type: ignore[index]
            }
            for name, result in results.items()
        ),
        key=lambda item: (
            item["f1"],
            -1.0 if item["auc"] is None else item["auc"],
            item["accuracy"],
        ),
        reverse=True,
    )

    payload = {
        "dataset": {
            "real_dir": str(real_dir),
            "fake_dir": str(fake_dir),
            "real_count": len(real_images),
            "fake_count": len(fake_images),
        },
        "threshold": args.threshold,
        "models": results,
        "ranking": ranking,
        "head_to_head": head_to_head_summary(results),
    }

    summary = {
        "dataset": payload["dataset"],
        "threshold": payload["threshold"],
        "ranking": payload["ranking"],
        "metrics": {
            name: result["metrics"]
            for name, result in results.items()
        },
        "head_to_head": payload["head_to_head"],
    }
    print(json.dumps(summary, indent=2))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote comparison JSON to {args.output_json}")


if __name__ == "__main__":
    main()
