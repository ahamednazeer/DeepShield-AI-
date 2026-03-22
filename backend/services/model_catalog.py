from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
MODELS_DIR = BACKEND_DIR / "models"
REFERENCE_REPO_DIR = PROJECT_ROOT / "Deepfake_detection_using_deep_learning-master"


IMAGE_AUTO_ORDER = [
    "final_model.keras",
    "deepfake_cnn.keras",
    "deepfake.keras",
    "model.h5",
    "deepfake20.h5",
]

VIDEO_AUTO_ORDER = [
    "model.h5",
    "final_model.keras",
    "deepfake.keras",
]

def _model_path(filename: str) -> Path:
    return MODELS_DIR / filename


def _has_timm() -> bool:
    return importlib.util.find_spec("timm") is not None


IMAGE_MODELS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "label": "Auto (recommended)",
        "description": "Use the backend default image model order.",
        "recommended": True,
    },
    {
        "id": "multimodal-fusion",
        "label": "Multimodal Fusion",
        "description": "Fuse the selected image checkpoint with forensic heuristics (ELA, FFT, color).",
        "pipeline_mode": "multimodal_fusion",
        "requires_default_path": True,
    },
    {
        "id": "frequency-domain",
        "label": "Frequency Domain Model",
        "description": "Run the FFT-based forensic frequency detector only.",
        "pipeline_mode": "frequency_only",
        "available": True,
    },
    {
        "id": "vit-base-pretrained",
        "label": "ViT Base (Pretrained)",
        "description": "ImageNet-pretrained ViT backbone used as an experimental image-analysis signal.",
        "backend": "torch",
        "reference_impl": "vit_pretrained",
        "model_name": "vit_base_patch16_224",
        "image_size": 224,
        "fake_index": 1,
        "pretrained_weights": True,
        "experimental": True,
        "pipeline_mode": "multimodal_fusion",
    },
    {
        "id": "deit-small-pretrained",
        "label": "DeiT Small (Pretrained)",
        "description": "ImageNet-pretrained DeiT backbone used as an experimental image-analysis signal.",
        "backend": "torch",
        "reference_impl": "vit_pretrained",
        "model_name": "deit_small_patch16_224",
        "image_size": 224,
        "fake_index": 1,
        "pretrained_weights": True,
        "experimental": True,
        "pipeline_mode": "multimodal_fusion",
    },
    {
        "id": "final_model.keras",
        "label": "Xception Final Model",
        "description": "Binary Keras image detector from the local training run.",
    },
    {
        "id": "deepfake_cnn.keras",
        "label": "Deepfake CNN",
        "description": "Custom CNN image detector.",
    },
    {
        "id": "deepfake.keras",
        "label": "Deepfake Keras",
        "description": "Alternative Keras image detector.",
    },
    {
        "id": "model.h5",
        "label": "ResNet H5",
        "description": "Legacy H5 checkpoint with compatibility loading.",
        "experimental": True,
    },
    {
        "id": "deepfake20.h5",
        "label": "Deepfake20 H5",
        "description": "Legacy H5 checkpoint that may be incomplete.",
        "experimental": True,
    },
]


VIDEO_MODELS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "label": "Auto (recommended)",
        "description": "Use the backend default video model order.",
        "recommended": True,
    },
    {
        "id": "multimodal-fusion",
        "label": "Multimodal Fusion",
        "description": "Fuse the selected video checkpoint with temporal and frame-level forensic signals.",
        "pipeline_mode": "multimodal_fusion",
        "requires_default_path": True,
        "reference_only": False,
    },
    {
        "id": "temporal-video-model",
        "label": "Temporal Video Model",
        "description": "Run the temporal consistency and per-frame forensic pipeline without a learned checkpoint.",
        "pipeline_mode": "temporal_only",
        "available": True,
        "reference_only": False,
        "process_all_frames": False,
        "frame_selection": "uniform",
    },
    {
        "id": "frequency-domain-model",
        "label": "Frequency Domain Model",
        "description": "Run spectral/frequency analysis across sampled video frames only.",
        "pipeline_mode": "frequency_only",
        "available": True,
        "reference_only": False,
        "process_all_frames": False,
        "frame_selection": "uniform",
    },
    {
        "id": "model_97_acc_100_frames_FF_data.pt",
        "label": "ResNeXt + LSTM (100 frames)",
        "description": "Reference PyTorch sequence model based on Deepfake_detection_using_deep_learning-master.",
        "backend": "torch",
        "reference_impl": "deep_learning_master",
        "fake_index": 0,
        "num_frames": 100,
        "image_size": 112,
        "frame_selection": "first",
        "process_all_frames": False,
    },
    {
        "id": "model.h5",
        "label": "ResNet H5",
        "description": "Legacy ResNet50-based Keras checkpoint.",
        "backend": "keras",
        "keras_preprocess": "resnet",
        "fake_index": 1,
        "image_size": 224,
        "experimental": True,
    },
    {
        "id": "final_model.keras",
        "label": "Final Keras",
        "description": "Binary Keras checkpoint for frame-level inference.",
        "backend": "keras",
        "keras_preprocess": "densenet",
        "fake_index": 1,
        "image_size": 224,
    },
    {
        "id": "deepfake.keras",
        "label": "Deepfake Keras",
        "description": "Alternative Keras video checkpoint.",
        "backend": "keras",
        "keras_preprocess": "densenet",
        "fake_index": 1,
        "image_size": 224,
    },
    {
        "id": "deepfake20.h5",
        "label": "Deepfake20 H5",
        "description": "Legacy H5 checkpoint that may not load cleanly.",
        "backend": "keras",
        "keras_preprocess": "resnet",
        "fake_index": 1,
        "image_size": 224,
        "experimental": True,
    },
    {
        "id": "vit-base-pretrained",
        "label": "ViT Base (Pretrained)",
        "description": "ImageNet-pretrained ViT backbone used as an experimental frame-level video signal.",
        "backend": "torch",
        "reference_impl": "vit_pretrained",
        "model_name": "vit_base_patch16_224",
        "image_size": 224,
        "fake_index": 1,
        "pretrained_weights": True,
        "process_all_frames": False,
        "frame_selection": "uniform",
        "experimental": True,
    },
    {
        "id": "deit-small-pretrained",
        "label": "DeiT Small (Pretrained)",
        "description": "ImageNet-pretrained DeiT backbone used as an experimental frame-level video signal.",
        "backend": "torch",
        "reference_impl": "vit_pretrained",
        "model_name": "deit_small_patch16_224",
        "image_size": 224,
        "fake_index": 1,
        "pretrained_weights": True,
        "process_all_frames": False,
        "frame_selection": "uniform",
        "experimental": True,
    },
]


CATALOG = {
    "image": IMAGE_MODELS,
    "video": VIDEO_MODELS,
    "audio": [],
}


def _auto_default_for(media_type: str) -> str | None:
    order = IMAGE_AUTO_ORDER if media_type == "image" else VIDEO_AUTO_ORDER if media_type == "video" else []
    for filename in order:
        if _model_path(filename).exists():
            return filename
    return None


def list_media_models(media_type: str) -> list[dict[str, Any]]:
    if media_type not in CATALOG:
        raise ValueError(f"Unsupported media type '{media_type}'.")

    models: list[dict[str, Any]] = []
    default_id = _auto_default_for(media_type)
    for entry in CATALOG[media_type]:
        item = dict(entry)
        model_id = item["id"]
        if model_id == "auto":
            item["available"] = default_id is not None
            item["resolved_default"] = default_id
        elif item.get("pipeline_mode") and not item.get("backend") and not item.get("requires_default_path"):
            item["available"] = bool(item.get("available", True))
        elif item.get("pretrained_weights"):
            item["available"] = _has_timm()
        elif item.get("requires_default_path"):
            item["available"] = default_id is not None
            item["resolved_default"] = default_id
        else:
            path = _model_path(model_id)
            item["available"] = path.exists()
            item["filename"] = model_id
            item["path"] = str(path)
        models.append(item)
    return models


def resolve_selected_model(media_type: str, selected_model: str | None) -> str | None:
    if media_type == "audio":
        return None

    normalized = (selected_model or "auto").strip() or "auto"
    options = {entry["id"]: entry for entry in list_media_models(media_type)}
    if normalized not in options:
        raise ValueError(f"Unsupported {media_type} model '{normalized}'.")

    if normalized == "auto":
        resolved = _auto_default_for(media_type)
        if resolved is None:
            raise ValueError(f"No available {media_type} model was found in backend/models.")
        return "auto"

    if not options[normalized]["available"]:
        raise ValueError(f"Requested {media_type} model '{normalized}' is not available on disk.")
    return normalized


def resolve_media_model_runtime(media_type: str, selected_model: str | None) -> dict[str, Any] | None:
    if media_type == "audio":
        return None

    requested = resolve_selected_model(media_type, selected_model)
    resolved_id = _auto_default_for(media_type) if requested == "auto" else requested
    if resolved_id is None:
        raise ValueError(f"No available {media_type} model was found in backend/models.")

    base_entry = next(
        (dict(entry) for entry in CATALOG[media_type] if entry["id"] == resolved_id),
        None,
    )
    if base_entry is None:
        raise ValueError(f"Model '{resolved_id}' is not registered for {media_type}.")

    runtime = dict(base_entry)
    runtime["requested_model"] = requested or "auto"
    runtime["resolved_model"] = resolved_id
    runtime["reference_dir"] = REFERENCE_REPO_DIR

    if runtime.get("requires_default_path"):
        default_id = _auto_default_for(media_type)
        if default_id is None:
            raise ValueError(f"No available {media_type} checkpoint was found for {resolved_id}.")
        runtime["resolved_model"] = default_id
        runtime["path"] = _model_path(default_id)
        runtime["filename"] = default_id
    elif runtime.get("pretrained_weights"):
        if not _has_timm():
            raise ValueError("timm is not installed, so pretrained ViT/DeiT models are unavailable.")
        runtime["path"] = None
        runtime["filename"] = runtime.get("model_name") or resolved_id
    elif runtime.get("pipeline_mode") and not runtime.get("backend"):
        runtime["path"] = None
        runtime["filename"] = None
    else:
        path = _model_path(resolved_id)
        if not path.exists():
            raise ValueError(f"Model file not found: {path}")
        runtime["path"] = path
        runtime["filename"] = resolved_id

    return runtime
