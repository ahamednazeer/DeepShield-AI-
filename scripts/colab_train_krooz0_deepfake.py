#!/usr/bin/env python3
"""
Colab-ready training script for pulling the Kaggle kernel
`krooz0/deep-fake-detection-on-images-and-videos` and training your own
fake-vs-real image classifier.

Intended usage in Colab:

1. Upload this file or clone the repo.
2. Upload `kaggle.json` to Colab or set `KAGGLE_USERNAME` / `KAGGLE_KEY`.
3. Provide a dataset using one of:
   - `--kaggle-dataset owner/dataset-slug`
   - `--dataset-archive /content/your_dataset.zip`
   - `--dataset-source-dir /content/drive/MyDrive/your_dataset_folder`
   - or point `--data-dir` at a dataset that already contains either:
   - `real/` and `fake/`, or
   - `train/real`, `train/fake`, `val/real`, `val/fake`
4. Run:

   !python scripts/colab_train_krooz0_deepfake.py \
       --data-dir /content/data \
       --output-dir /content/output \
       --epochs 10

Optional Kaggle dataset download:

   !python scripts/colab_train_krooz0_deepfake.py \
       --kaggle-dataset your-owner/your-dataset \
       --data-dir /content/data \
       --output-dir /content/output

This script pulls the referenced Kaggle notebook for reference and export,
but trains a clean binary classifier in Colab instead of trying to execute
the full notebook end-to-end.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile


KAGGLE_KERNEL_SLUG = "krooz0/deep-fake-detection-on-images-and-videos"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def pip_install(packages: Iterable[str]) -> None:
    run([sys.executable, "-m", "pip", "install", "-q", *packages])


def ensure_colab_deps() -> None:
    pip_install(
        [
            "kaggle",
            "nbformat",
            "nbconvert",
            "tensorflow>=2.16,<2.21",
            "matplotlib",
            "pandas",
            "scikit-learn",
        ]
    )


def configure_kaggle_credentials(kaggle_json: Path | None) -> None:
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    target = kaggle_dir / "kaggle.json"

    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        payload = {
            "username": os.environ["KAGGLE_USERNAME"],
            "key": os.environ["KAGGLE_KEY"],
        }
        target.write_text(json.dumps(payload))
        target.chmod(0o600)
        return

    if kaggle_json and kaggle_json.exists():
        shutil.copy2(kaggle_json, target)
        target.chmod(0o600)
        return

    raise FileNotFoundError(
        "Kaggle credentials not found. Upload kaggle.json or set "
        "KAGGLE_USERNAME and KAGGLE_KEY."
    )


def pull_kaggle_kernel(work_dir: Path) -> dict[str, Path | None]:
    kernel_dir = work_dir / "kaggle_kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)

    run(["kaggle", "kernels", "pull", KAGGLE_KERNEL_SLUG, "-p", str(kernel_dir), "-m"])

    notebook = next(kernel_dir.glob("*.ipynb"), None)
    script = next(kernel_dir.glob("*.py"), None)
    metadata = next(kernel_dir.glob("*.json"), None)

    if notebook is not None and script is None:
        run(
            [
                "jupyter",
                "nbconvert",
                "--to",
                "script",
                str(notebook),
                "--output-dir",
                str(kernel_dir),
            ]
        )
        script = next(kernel_dir.glob("*.py"), None)

    print("\nPulled kernel assets:")
    print(f"- notebook: {notebook}")
    print(f"- script:   {script}")
    print(f"- metadata: {metadata}")
    return {
        "kernel_dir": kernel_dir,
        "notebook": notebook,
        "script": script,
        "metadata": metadata,
    }


def infer_kaggle_dataset_from_kernel_assets(kernel_assets: dict[str, Path | None]) -> str | None:
    metadata = kernel_assets.get("metadata")
    if metadata is None or not metadata.exists():
        return None

    payload = json.loads(metadata.read_text())
    dataset_sources = payload.get("dataset_sources") or []
    if dataset_sources:
        inferred = str(dataset_sources[0])
        print(f"\nInferred Kaggle dataset from kernel metadata: {inferred}")
        return inferred
    return None


def maybe_download_kaggle_dataset(dataset_slug: str | None, data_dir: Path) -> None:
    if not dataset_slug:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / "dataset.zip"
    run(["kaggle", "datasets", "download", "-d", dataset_slug, "-p", str(data_dir)])

    zip_candidates = sorted(data_dir.glob("*.zip"))
    if not zip_candidates:
        raise FileNotFoundError("Kaggle dataset download completed but no .zip file was found.")

    archive = zip_candidates[-1]
    print(f"\nExtracting dataset archive: {archive}")
    with ZipFile(archive, "r") as zf:
        zf.extractall(data_dir)


def maybe_extract_dataset_archive(dataset_archive: Path | None, data_dir: Path) -> None:
    if dataset_archive is None:
        return

    if not dataset_archive.exists():
        raise FileNotFoundError(f"Dataset archive not found: {dataset_archive}")

    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nExtracting dataset archive: {dataset_archive}")
    with ZipFile(dataset_archive, "r") as zf:
        zf.extractall(data_dir)


def maybe_copy_dataset_dir(dataset_source_dir: Path | None, data_dir: Path) -> None:
    if dataset_source_dir is None:
        return

    if not dataset_source_dir.exists():
        raise FileNotFoundError(f"Dataset source directory not found: {dataset_source_dir}")

    if dataset_source_dir.resolve() == data_dir.resolve():
        print("\nDataset source already matches data dir. No copy needed.")
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nCopying dataset contents from {dataset_source_dir} to {data_dir}")
    for item in dataset_source_dir.iterdir():
        target = data_dir / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def detect_dataset_layout(data_dir: Path) -> dict[str, Path]:
    train_dir = data_dir / "train"
    val_dir = data_dir / "val"
    if (train_dir / "real").exists() and (train_dir / "fake").exists():
        result = {"train": train_dir}
        if (val_dir / "real").exists() and (val_dir / "fake").exists():
            result["val"] = val_dir
        return result

    if (data_dir / "real").exists() and (data_dir / "fake").exists():
        return {"all": data_dir}

    candidates = []
    for path in data_dir.rglob("*"):
        if not path.is_dir():
            continue
        child_names = {child.name.lower() for child in path.iterdir() if child.is_dir()}
        if {"real", "fake"}.issubset(child_names):
            candidates.append(path)

    if candidates:
        chosen = sorted(candidates, key=lambda p: len(p.parts))[0]
        return {"all": chosen}

    metadata_candidates = sorted(data_dir.rglob("metadata.csv"))
    for metadata_path in metadata_candidates:
        parent = metadata_path.parent
        for images_dir_name in ("faces_224", "faces", "images"):
            images_dir = parent / images_dir_name
            if images_dir.exists() and images_dir.is_dir():
                return {"metadata": metadata_path, "images_dir": images_dir}

    raise FileNotFoundError(
        f"Could not find a dataset layout under {data_dir}. "
        "Expected either `real/` and `fake/`, `train/real` and `train/fake`, "
        "or a metadata dataset such as `metadata.csv` + `faces_224/`."
    )


def build_model(backbone: str, image_size: int, learning_rate: float):
    import tensorflow as tf

    backbone = backbone.lower()
    input_shape = (image_size, image_size, 3)

    if backbone == "vgg16":
        base = tf.keras.applications.VGG16(
            include_top=False,
            weights="imagenet",
            input_shape=input_shape,
        )
        preprocess = tf.keras.applications.vgg16.preprocess_input
    elif backbone == "xception":
        base = tf.keras.applications.Xception(
            include_top=False,
            weights="imagenet",
            input_shape=input_shape,
        )
        preprocess = tf.keras.applications.xception.preprocess_input
    elif backbone == "mobilenetv2":
        base = tf.keras.applications.MobileNetV2(
            include_top=False,
            weights="imagenet",
            input_shape=input_shape,
        )
        preprocess = tf.keras.applications.mobilenet_v2.preprocess_input
    elif backbone == "efficientnetb0":
        base = tf.keras.applications.EfficientNetB0(
            include_top=False,
            weights="imagenet",
            input_shape=input_shape,
        )
        preprocess = tf.keras.applications.efficientnet.preprocess_input
    else:
        raise ValueError(f"Unsupported backbone: {backbone}")

    base.trainable = False

    inputs = tf.keras.Input(shape=input_shape)
    x = tf.keras.layers.Lambda(preprocess, name="preprocess")(inputs)
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.35)(x)
    x = tf.keras.layers.Dense(256, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.25)(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="fake_probability")(x)
    model = tf.keras.Model(inputs, outputs, name=f"{backbone}_deepfake_binary")

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="binary_crossentropy",
        metrics=[
            "accuracy",
            tf.keras.metrics.AUC(name="auc"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
        ],
    )
    return model, base


def make_datasets(
    data_layout: dict[str, Path],
    image_size: int,
    batch_size: int,
    seed: int,
):
    import pandas as pd
    import tensorflow as tf
    from sklearn.model_selection import train_test_split

    image_dims = (image_size, image_size)

    if "metadata" in data_layout:
        metadata = pd.read_csv(data_layout["metadata"])
        images_dir = data_layout["images_dir"]

        filename_col = next(
            (
                column
                for column in ("videoname", "filename", "file", "image", "path")
                if column in metadata.columns
            ),
            None,
        )
        label_col = next(
            (
                column
                for column in ("label", "class", "target")
                if column in metadata.columns
            ),
            None,
        )

        if filename_col is None or label_col is None:
            raise ValueError(
                f"Unsupported metadata columns in {data_layout['metadata']}. "
                f"Found columns: {list(metadata.columns)}"
            )

        def resolve_image_path(name: str) -> str | None:
            raw_name = str(name)
            stem = Path(raw_name).stem
            candidates = [
                images_dir / raw_name,
                images_dir / f"{stem}.jpg",
                images_dir / f"{stem}.jpeg",
                images_dir / f"{stem}.png",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
            matches = sorted(images_dir.glob(f"{stem}.*"))
            if matches:
                return str(matches[0])
            return None

        metadata = metadata[[filename_col, label_col]].copy()
        metadata["file_path"] = metadata[filename_col].map(resolve_image_path)
        metadata["label_name"] = metadata[label_col].astype(str).str.strip().str.upper()
        metadata["label_num"] = metadata["label_name"].map(
            {
                "REAL": 0.0,
                "FAKE": 1.0,
                "0": 0.0,
                "1": 1.0,
            }
        )
        metadata = metadata.dropna(subset=["file_path", "label_num"]).reset_index(drop=True)
        if metadata.empty:
            raise FileNotFoundError(
                f"No labeled images could be resolved from {data_layout['metadata']} "
                f"and {images_dir}."
            )

        stratify = metadata["label_num"] if metadata["label_num"].nunique() > 1 else None
        train_df, val_df = train_test_split(
            metadata,
            test_size=0.2,
            random_state=seed,
            stratify=stratify,
        )

        def make_tensor_dataset(frame, shuffle: bool):
            paths = frame["file_path"].astype(str).tolist()
            labels = frame["label_num"].astype("float32").tolist()
            dataset = tf.data.Dataset.from_tensor_slices((paths, labels))
            if shuffle:
                dataset = dataset.shuffle(len(paths), seed=seed, reshuffle_each_iteration=True)

            def load_example(path, label):
                image = tf.io.read_file(path)
                image = tf.io.decode_image(image, channels=3, expand_animations=False)
                image = tf.image.resize(image, image_dims)
                image = tf.cast(image, tf.float32)
                label = tf.reshape(tf.cast(label, tf.float32), (1,))
                return image, label

            dataset = dataset.map(load_example, num_parallel_calls=tf.data.AUTOTUNE)
            dataset = dataset.batch(batch_size)
            dataset = dataset.prefetch(tf.data.AUTOTUNE)
            return dataset

        train_ds = make_tensor_dataset(train_df, shuffle=True)
        val_ds = make_tensor_dataset(val_df, shuffle=False)
        class_names = ["real", "fake"]
        return train_ds, val_ds, class_names

    if "train" in data_layout:
        train_ds = tf.keras.utils.image_dataset_from_directory(
            data_layout["train"],
            labels="inferred",
            label_mode="binary",
            batch_size=batch_size,
            image_size=image_dims,
            shuffle=True,
            seed=seed,
        )
        if "val" in data_layout:
            val_ds = tf.keras.utils.image_dataset_from_directory(
                data_layout["val"],
                labels="inferred",
                label_mode="binary",
                batch_size=batch_size,
                image_size=image_dims,
                shuffle=False,
            )
        else:
            raise ValueError("Training directory exists but validation directory is missing.")
    else:
        train_ds = tf.keras.utils.image_dataset_from_directory(
            data_layout["all"],
            labels="inferred",
            label_mode="binary",
            batch_size=batch_size,
            image_size=image_dims,
            validation_split=0.2,
            subset="training",
            seed=seed,
        )
        val_ds = tf.keras.utils.image_dataset_from_directory(
            data_layout["all"],
            labels="inferred",
            label_mode="binary",
            batch_size=batch_size,
            image_size=image_dims,
            validation_split=0.2,
            subset="validation",
            seed=seed,
        )

    class_names = list(train_ds.class_names)
    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(autotune)
    val_ds = val_ds.prefetch(autotune)
    return train_ds, val_ds, class_names


def train_model(
    model,
    base_model,
    train_ds,
    val_ds,
    output_dir: Path,
    epochs: int,
    finetune_epochs: int,
    learning_rate: float,
):
    import tensorflow as tf

    output_dir.mkdir(parents=True, exist_ok=True)
    best_model_path = output_dir / "best_model.keras"

    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(best_model_path),
            monitor="val_auc",
            mode="max",
            save_best_only=True,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_auc",
            mode="max",
            patience=3,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=2,
            min_lr=1e-6,
        ),
    ]

    print("\nStarting warmup training...")
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
        callbacks=callbacks,
    )

    if finetune_epochs > 0:
        print("\nStarting fine-tuning...")
        base_model.trainable = True
        if len(base_model.layers) > 20:
            for layer in base_model.layers[:-20]:
                layer.trainable = False

        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate / 10.0),
            loss="binary_crossentropy",
            metrics=[
                "accuracy",
                tf.keras.metrics.AUC(name="auc"),
                tf.keras.metrics.Precision(name="precision"),
                tf.keras.metrics.Recall(name="recall"),
            ],
        )
        fine_history = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=epochs + finetune_epochs,
            initial_epoch=history.epoch[-1] + 1 if history.epoch else 0,
            callbacks=callbacks,
        )

        for key, values in fine_history.history.items():
            history.history.setdefault(key, []).extend(values)

    final_model_path = output_dir / "final_model.keras"
    model.save(final_model_path)

    history_path = output_dir / "history.json"
    history_path.write_text(json.dumps(history.history, indent=2))

    eval_metrics = model.evaluate(val_ds, return_dict=True)
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(eval_metrics, indent=2))

    return {
        "best_model": best_model_path,
        "final_model": final_model_path,
        "history": history_path,
        "metrics": metrics_path,
        "eval": eval_metrics,
    }


def maybe_mount_drive() -> None:
    try:
        from google.colab import drive  # type: ignore
    except ImportError:
        return
    drive.mount("/content/drive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull Kaggle kernel and train your own deepfake image model in Colab.")
    parser.add_argument("--data-dir", type=Path, required=True, help="Dataset root directory.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where to save models and logs.")
    parser.add_argument("--work-dir", type=Path, default=Path("/content/work"), help="Working directory for pulled kernel files.")
    parser.add_argument("--kaggle-json", type=Path, default=Path("/content/kaggle.json"), help="Path to kaggle.json if not using env vars.")
    parser.add_argument("--kaggle-dataset", type=str, default=None, help="Optional Kaggle dataset slug to download first.")
    parser.add_argument("--dataset-archive", type=Path, default=None, help="Optional path to a dataset zip archive.")
    parser.add_argument("--dataset-source-dir", type=Path, default=None, help="Optional path to an existing dataset directory.")
    parser.add_argument(
        "--backbone",
        type=str,
        default="xception",
        choices=["xception", "vgg16", "mobilenetv2", "efficientnetb0"],
    )
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--finetune-epochs", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mount-drive", action="store_true", help="Mount Google Drive when running in Colab.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mount_drive:
        maybe_mount_drive()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    ensure_colab_deps()
    configure_kaggle_credentials(args.kaggle_json if args.kaggle_json.exists() else None)
    kernel_assets = pull_kaggle_kernel(args.work_dir)
    effective_kaggle_dataset = args.kaggle_dataset or infer_kaggle_dataset_from_kernel_assets(kernel_assets)

    maybe_copy_dataset_dir(args.dataset_source_dir, args.data_dir)
    maybe_extract_dataset_archive(args.dataset_archive, args.data_dir)
    maybe_download_kaggle_dataset(effective_kaggle_dataset, args.data_dir)
    data_layout = detect_dataset_layout(args.data_dir)
    print(f"\nDetected dataset layout: {data_layout}")

    train_ds, val_ds, class_names = make_datasets(
        data_layout=data_layout,
        image_size=args.image_size,
        batch_size=args.batch_size,
        seed=args.seed,
    )
    (args.output_dir / "class_names.json").write_text(json.dumps(class_names, indent=2))

    model, base = build_model(
        backbone=args.backbone,
        image_size=args.image_size,
        learning_rate=args.learning_rate,
    )
    model.summary()

    artifacts = train_model(
        model=model,
        base_model=base,
        train_ds=train_ds,
        val_ds=val_ds,
        output_dir=args.output_dir,
        epochs=args.epochs,
        finetune_epochs=args.finetune_epochs,
        learning_rate=args.learning_rate,
    )

    summary = {
        "kernel_dir": str(kernel_assets["kernel_dir"]),
        "kernel_notebook": str(kernel_assets["notebook"]) if kernel_assets["notebook"] else None,
        "kernel_script": str(kernel_assets["script"]) if kernel_assets["script"] else None,
        "kaggle_dataset": effective_kaggle_dataset,
        "class_names": class_names,
        "artifacts": {key: str(value) if isinstance(value, Path) else value for key, value in artifacts.items()},
    }
    summary_path = args.output_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    print("\nTraining complete.")
    print(f"- Pulled kernel dir: {kernel_assets['kernel_dir']}")
    print(f"- Best model:        {artifacts['best_model']}")
    print(f"- Final model:       {artifacts['final_model']}")
    print(f"- Metrics:           {artifacts['metrics']}")
    print(f"- Summary:           {summary_path}")
    print(f"- Validation eval:   {artifacts['eval']}")


if __name__ == "__main__":
    main()
