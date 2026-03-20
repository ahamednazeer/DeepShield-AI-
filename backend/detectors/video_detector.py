"""
Video Deepfake Detection Pipeline
Extracts frames, detects faces, analyzes per-frame artifacts, and checks
temporal consistency across the video.
"""

import os
import sys
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, Tuple, Callable, List

# Use legacy Keras for older .h5 models
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")


# Use Haar cascade for face detection (built-in to OpenCV, no extra models needed)
HAAR_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

# Video model configuration
ROOT_DIR = Path(__file__).resolve().parents[2]
REF_DIR = Path(os.getenv(
    "VIDEO_REFERENCE_DIR",
    str(ROOT_DIR / "Deepfake-Detection-master"),
))
MODEL_PATH = Path(os.getenv(
    "VIDEO_MODEL_PATH",
    str(Path(__file__).resolve().parent.parent / "models" / "model.h5"),
))
MODEL_BACKEND = os.getenv("VIDEO_MODEL_BACKEND", "auto").lower()
MODEL_KERAS_PREPROCESS = os.getenv("VIDEO_KERAS_PREPROCESS", "densenet").lower()
MODEL_NAME = os.getenv("VIDEO_TORCH_MODEL_NAME", "xception")
MODEL_DROPOUT = float(os.getenv("VIDEO_TORCH_MODEL_DROPOUT", "0.5"))
MODEL_NUM_FRAMES = int(os.getenv("VIDEO_MODEL_NUM_FRAMES", "15"))
MODEL_IMAGE_SIZE = int(os.getenv("VIDEO_MODEL_IMAGE_SIZE", "224"))
MODEL_FAKE_INDEX = int(os.getenv("VIDEO_MODEL_FAKE_INDEX", "1"))
MODEL_STRICT = os.getenv("VIDEO_MODEL_STRICT", "0") == "1"
MODEL_FACE_MARGIN = float(os.getenv("VIDEO_MODEL_FACE_MARGIN", "0.2"))
FACE_COVERAGE_THRESHOLD = float(os.getenv("VIDEO_FACE_COVERAGE_THRESHOLD", "0.6"))
FACE_COVERAGE_MIN = float(os.getenv("VIDEO_FACE_COVERAGE_MIN", "0.3"))
FUSION_MODEL_WEIGHT_STRONG = float(os.getenv("VIDEO_FUSION_MODEL_WEIGHT_STRONG", "0.8"))
FUSION_MODEL_WEIGHT_WEAK = float(os.getenv("VIDEO_FUSION_MODEL_WEIGHT_WEAK", "0.4"))
VERDICT_MANIPULATED = float(os.getenv("VIDEO_VERDICT_MANIPULATED", "0.65"))
VERDICT_SUSPICIOUS = float(os.getenv("VIDEO_VERDICT_SUSPICIOUS", "0.35"))
HEURISTIC_AGREEMENT_REF = float(os.getenv("VIDEO_HEURISTIC_AGREEMENT_REF", "0.4"))
MODEL_WEIGHT_MIN_FACTOR = float(os.getenv("VIDEO_MODEL_WEIGHT_MIN_FACTOR", "0.5"))
MODEL_BATCH_SIZE = int(os.getenv("VIDEO_MODEL_BATCH_SIZE", "8"))
REFERENCE_ONLY = os.getenv("VIDEO_REFERENCE_ONLY", "1") == "1"
PROCESS_ALL_FRAMES = os.getenv("VIDEO_PROCESS_ALL_FRAMES", "1") == "1"
PROGRESS_EVERY = int(os.getenv("VIDEO_PROGRESS_EVERY", "5"))
KERAS_AGG = os.getenv("VIDEO_KERAS_AGG", "gated_max").lower()
KERAS_TOPK = float(os.getenv("VIDEO_KERAS_TOPK", "0.2"))
KERAS_MAX_GATE = float(os.getenv("VIDEO_KERAS_MAX_GATE", "0.9"))
KERAS_MEAN_GATE = float(os.getenv("VIDEO_KERAS_MEAN_GATE", "0.25"))
KERAS_MAX_WEIGHT = float(os.getenv("VIDEO_KERAS_MAX_WEIGHT", "0.5"))

_TORCH_MODEL = None
_TORCH_MODEL_ERROR: Optional[str] = None
_TORCH_MODEL_WARN: Optional[str] = None
_PREPROCESS = None
_KERAS_MODEL = None
_KERAS_ERROR: Optional[str] = None
_KERAS_INPUT_SHAPE: Optional[Tuple[int, int]] = None
_DLIB_DETECTOR = None
_DLIB_ERROR: Optional[str] = None


def extract_frames(video_path: str, fps_target: int = 2, max_frames: int = 30) -> list:
    """Extract frames from video at target FPS."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = max(1, int(video_fps / fps_target))

    frames = []
    frame_idx = 0

    while cap.isOpened() and len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            frames.append({"index": frame_idx, "frame": frame})
        frame_idx += 1

    cap.release()
    return frames


def extract_uniform_frames(video_path: str, num_frames: int) -> list:
    """Extract a fixed number of frames uniformly across the video."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frames = []

    if total_frames > 0:
        indices = np.linspace(0, max(total_frames - 1, 0), num_frames).astype(int).tolist()
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret:
                break
            frames.append({"index": int(idx), "frame": frame})
    else:
        idx = 0
        while len(frames) < num_frames and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frames.append({"index": idx, "frame": frame})
            idx += 1

    cap.release()

    if not frames:
        return []

    while len(frames) < num_frames:
        frames.append(frames[-1])

    return frames


def extract_all_frames(
    video_path: str,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> list:
    """Extract all frames from a video sequentially."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    total_hint = total_frames if total_frames > 0 else None
    progress_every = max(PROGRESS_EVERY, 1)
    if on_progress:
        on_progress(0, total_hint)

    frames = []
    idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frames.append({"index": idx, "frame": frame})
        idx += 1
        if on_progress and (idx % progress_every == 0 or (total_frames and idx >= total_frames)):
            on_progress(idx, total_hint)

    cap.release()
    if on_progress:
        on_progress(idx, total_hint)
    return frames


def _ensure_reference_importable() -> Optional[str]:
    if not REF_DIR.exists():
        return f"Reference repo not found at {REF_DIR}"
    if str(REF_DIR) not in sys.path:
        sys.path.insert(0, str(REF_DIR))
    return None


def _use_keras_backend() -> bool:
    if MODEL_BACKEND in ("keras", "tf", "tensorflow"):
        return True
    if MODEL_BACKEND in ("torch", "pytorch"):
        return False
    return MODEL_PATH.suffix.lower() in (".h5", ".keras")


def _load_keras_model() -> Tuple[Optional[object], Optional[str]]:
    """Lazy-load Keras .h5/.keras model."""
    global _KERAS_MODEL, _KERAS_ERROR, _KERAS_INPUT_SHAPE

    if _KERAS_MODEL is not None:
        return _KERAS_MODEL, None
    if _KERAS_ERROR:
        return None, _KERAS_ERROR

    if not MODEL_PATH.exists():
        _KERAS_ERROR = f"Model file not found at {MODEL_PATH}"
        return None, _KERAS_ERROR

    try:
        import tensorflow as tf
        model = tf.keras.models.load_model(str(MODEL_PATH), compile=False)
        _KERAS_MODEL = model

        shape = model.input_shape
        if isinstance(shape, list):
            shape = shape[0]
        if shape is None or len(shape) < 4:
            _KERAS_INPUT_SHAPE = None
        else:
            _KERAS_INPUT_SHAPE = (int(shape[1]), int(shape[2]))
        return _KERAS_MODEL, None
    except Exception as e:
        _KERAS_ERROR = str(e)
        return None, _KERAS_ERROR


def _keras_preprocess_batch(batch: np.ndarray) -> np.ndarray:
    if MODEL_KERAS_PREPROCESS == "densenet":
        from tensorflow.keras.applications.densenet import preprocess_input
        return preprocess_input(batch)
    if MODEL_KERAS_PREPROCESS == "resnet":
        from tensorflow.keras.applications.resnet import preprocess_input
        return preprocess_input(batch)
    if MODEL_KERAS_PREPROCESS == "mobilenet":
        from tensorflow.keras.applications.mobilenet import preprocess_input
        return preprocess_input(batch)
    return batch


def _aggregate_frame_probs(frame_probs: np.ndarray) -> float:
    mean_score = float(np.mean(frame_probs))
    max_score = float(np.max(frame_probs))
    if KERAS_AGG == "max":
        return max_score
    if KERAS_AGG == "topk":
        k = max(1, int(len(frame_probs) * KERAS_TOPK))
        topk = np.sort(frame_probs)[-k:]
        return float(np.mean(topk))
    if KERAS_AGG == "gated_max":
        if max_score >= KERAS_MAX_GATE and mean_score >= KERAS_MEAN_GATE:
            return float((1.0 - KERAS_MAX_WEIGHT) * mean_score + KERAS_MAX_WEIGHT * max_score)
        return mean_score
    return mean_score


def _predict_keras_model(frames: list) -> Tuple[Optional[float], Optional[list], Optional[list], Optional[str]]:
    """Run Keras model inference and return (fake_score, probs, frame_probs, error)."""
    model, err = _load_keras_model()
    if err:
        return None, None, None, err

    if not frames:
        return None, None, None, "No frames available for model inference."

    height, width = _KERAS_INPUT_SHAPE or (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)
    batch = []
    for item in frames[:MODEL_NUM_FRAMES]:
        frame = item["frame"] if isinstance(item, dict) else item
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
        batch.append(resized)

    x = np.asarray(batch, dtype=np.float32)
    x = _keras_preprocess_batch(x)

    preds = model.predict(x, verbose=0)
    preds = np.asarray(preds)

    if preds.ndim == 2 and preds.shape[1] == 1:
        frame_probs = preds.reshape(-1)
        agg_fake = _aggregate_frame_probs(frame_probs)
        probs_list = [round(1.0 - agg_fake, 6), round(agg_fake, 6)]
        return agg_fake, probs_list, [round(float(p), 6) for p in frame_probs.tolist()], None

    if preds.ndim == 2 and preds.shape[1] >= 2:
        # Assume logits or probabilities for 2 classes
        if preds.max() > 1.0 or preds.min() < 0.0:
            exps = np.exp(preds - np.max(preds, axis=1, keepdims=True))
            probs = exps / np.sum(exps, axis=1, keepdims=True)
        else:
            probs = preds
        fake_index = MODEL_FAKE_INDEX
        if fake_index < 0 or fake_index >= probs.shape[1]:
            fake_index = probs.shape[1] - 1
        frame_probs = probs[:, fake_index]
        agg_fake = _aggregate_frame_probs(frame_probs)
        probs_list = [round(float(p), 6) for p in np.mean(probs, axis=0).tolist()]
        return agg_fake, probs_list, [round(float(p), 6) for p in frame_probs.tolist()], None

    return None, None, None, f"Unexpected model output shape: {preds.shape}"


def _predict_keras_stream(
    video_path: str,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> Tuple[Optional[float], Optional[list], Optional[list], Optional[str], Optional[int], int, float]:
    """Stream Keras inference over all frames in a video."""
    model, err = _load_keras_model()
    if err:
        return None, None, None, err, None, 0, 0.0

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, None, None, f"Cannot open video: {video_path}", None, 0, 0.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    total_hint = total_frames if total_frames > 0 else None
    progress_every = max(PROGRESS_EVERY, 1)
    if on_progress:
        on_progress(0, total_hint)

    height, width = _KERAS_INPUT_SHAPE or (MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE)
    dlib_detector, _ = _get_dlib_detector()

    batch: List[np.ndarray] = []
    frame_probs: List[float] = []
    multi_sum = None
    multi_count = 0
    processed = 0
    face_found = 0

    def flush_batch(frames_batch: List[np.ndarray]) -> Optional[str]:
        nonlocal multi_sum, multi_count
        if not frames_batch:
            return None
        x = np.asarray(frames_batch, dtype=np.float32)
        x = _keras_preprocess_batch(x)
        preds = model.predict(x, verbose=0)
        preds = np.asarray(preds)

        if preds.ndim == 2 and preds.shape[1] == 1:
            frame_batch = preds.reshape(-1)
            frame_probs.extend(frame_batch.tolist())
            return None

        if preds.ndim == 2 and preds.shape[1] >= 2:
            if preds.max() > 1.0 or preds.min() < 0.0:
                exps = np.exp(preds - np.max(preds, axis=1, keepdims=True))
                probs = exps / np.sum(exps, axis=1, keepdims=True)
            else:
                probs = preds
            fake_index = MODEL_FAKE_INDEX
            if fake_index < 0 or fake_index >= probs.shape[1]:
                fake_index = probs.shape[1] - 1
            frame_batch = probs[:, fake_index]
            frame_probs.extend(frame_batch.tolist())
            batch_sum = probs.sum(axis=0)
            multi_sum = batch_sum if multi_sum is None else (multi_sum + batch_sum)
            multi_count += probs.shape[0]
            return None

        return f"Unexpected model output shape: {preds.shape}"

    error = None
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        processed += 1

        crop = None
        if dlib_detector is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = dlib_detector(gray, 1)
            if len(faces):
                face = max(
                    faces,
                    key=lambda r: max(0, (r.right() - r.left())) * max(0, (r.bottom() - r.top()))
                )
                height_img, width_img = frame.shape[:2]
                x, y, size = _get_boundingbox(face, width_img, height_img)
                crop = frame[y:y + size, x:x + size]
                if crop.size == 0:
                    crop = None

        if crop is None:
            crop = crop_largest_face(frame, detect_faces(frame), MODEL_FACE_MARGIN)

        if crop is not None:
            face_found += 1
            source = crop
        else:
            source = frame

        rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
        batch.append(resized)

        if len(batch) >= MODEL_BATCH_SIZE:
            error = flush_batch(batch)
            batch = []
            if error:
                break

        if on_progress and (processed % progress_every == 0 or (total_frames and processed >= total_frames)):
            on_progress(processed, total_hint)

    if error is None:
        error = flush_batch(batch)

    cap.release()

    if on_progress:
        on_progress(processed, total_hint)

    if error:
        return None, None, None, error, total_hint, processed, (face_found / processed) if processed else 0.0

    if not frame_probs:
        return None, None, None, "No model outputs generated.", total_hint, processed, (face_found / processed) if processed else 0.0

    agg_fake = _aggregate_frame_probs(np.asarray(frame_probs, dtype=np.float32))
    if multi_sum is not None and multi_count > 0:
        avg_probs = multi_sum / multi_count
        probs_list = [round(float(p), 6) for p in avg_probs.tolist()]
    else:
        probs_list = [round(1.0 - agg_fake, 6), round(agg_fake, 6)]

    return (
        agg_fake,
        probs_list,
        [round(float(p), 6) for p in frame_probs],
        None,
        total_hint,
        processed,
        (face_found / processed) if processed else 0.0,
    )


def _load_preprocess() -> Tuple[Optional[object], Optional[str]]:
    """Load preprocessing transform from the reference repo."""
    global _PREPROCESS

    if _PREPROCESS is not None:
        return _PREPROCESS, None

    err = _ensure_reference_importable()
    if err:
        return None, err

    try:
        from dataset.transform import xception_default_data_transforms
        _PREPROCESS = xception_default_data_transforms['test']
        return _PREPROCESS, None
    except Exception as e:
        return None, str(e)


def _load_video_model() -> Tuple[Optional[object], Optional[str]]:
    """Lazy-load the PyTorch video model (reference architecture)."""
    global _TORCH_MODEL, _TORCH_MODEL_ERROR, _TORCH_MODEL_WARN

    if _TORCH_MODEL is not None:
        return _TORCH_MODEL, None
    if _TORCH_MODEL_ERROR:
        return None, _TORCH_MODEL_ERROR

    if not MODEL_PATH.exists():
        _TORCH_MODEL_ERROR = f"Model file not found at {MODEL_PATH}"
        return None, _TORCH_MODEL_ERROR

    try:
        _TORCH_MODEL_WARN = None
        err = _ensure_reference_importable()
        if err:
            _TORCH_MODEL_ERROR = err
            return None, _TORCH_MODEL_ERROR

        import torch
        from network.models import model_selection

        model = model_selection(modelname=MODEL_NAME, num_out_classes=2, dropout=MODEL_DROPOUT)
        checkpoint = torch.load(str(MODEL_PATH), map_location="cpu")

        state_dict = None
        if isinstance(checkpoint, dict):
            if "state_dict" in checkpoint:
                state_dict = checkpoint["state_dict"]
            elif "model_state_dict" in checkpoint:
                state_dict = checkpoint["model_state_dict"]
            else:
                state_dict = checkpoint
        if not isinstance(state_dict, dict):
            _TORCH_MODEL_ERROR = "Unsupported checkpoint format (expected state_dict)."
            return None, _TORCH_MODEL_ERROR

        cleaned = {}
        for key, value in state_dict.items():
            if key.startswith("module."):
                cleaned[key[7:]] = value
            else:
                cleaned[key] = value

        missing, unexpected = model.load_state_dict(cleaned, strict=False)
        if missing or unexpected:
            _TORCH_MODEL_WARN = f"Missing keys: {len(missing)}, unexpected keys: {len(unexpected)}"

        if isinstance(model, torch.nn.DataParallel):
            model = model.module

        model.eval()
        _TORCH_MODEL = model
        return _TORCH_MODEL, None
    except Exception as e:
        _TORCH_MODEL_ERROR = str(e)
        return None, _TORCH_MODEL_ERROR


def _prepare_torch_batch(frames: list) -> Tuple[Optional[object], Optional[str]]:
    """Prepare a batch tensor for PyTorch model inference."""
    import torch
    from PIL import Image as pil_image

    preprocess, err = _load_preprocess()
    if err:
        return None, err

    processed = []
    for item in frames[:MODEL_NUM_FRAMES]:
        frame = item["frame"] if isinstance(item, dict) else item
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = pil_image.fromarray(rgb)
        tensor = preprocess(image)
        processed.append(tensor)

    if not processed:
        return None, "No frames available for preprocessing."

    return torch.stack(processed, dim=0), None


def _predict_video_model(frames: list) -> Tuple[Optional[float], Optional[list], Optional[list], Optional[str]]:
    """Run PyTorch model inference and return (fake_score, probs, frame_probs, error)."""
    model, err = _load_video_model()
    if err:
        return None, None, None, err

    try:
        import torch

        batch, prep_err = _prepare_torch_batch(frames)
        if prep_err:
            return None, None, None, prep_err

        fake_probs_all = []
        sum_probs = None
        count = 0

        for start in range(0, batch.shape[0], MODEL_BATCH_SIZE):
            chunk = batch[start:start + MODEL_BATCH_SIZE]
            with torch.no_grad():
                logits = model(chunk)

            if logits.ndim == 1:
                logits = logits.unsqueeze(0) if logits.numel() == 2 else logits.unsqueeze(1)

            if logits.shape[-1] == 1:
                probs = torch.sigmoid(logits).squeeze(-1)
                fake_probs = probs
                chunk_sum = probs.sum()
                sum_probs = chunk_sum if sum_probs is None else sum_probs + chunk_sum
            else:
                probs = torch.softmax(logits, dim=-1)
                fake_index = MODEL_FAKE_INDEX
                if fake_index < 0 or fake_index >= probs.shape[-1]:
                    fake_index = probs.shape[-1] - 1
                fake_probs = probs[:, fake_index]
                chunk_sum = probs.sum(dim=0)
                sum_probs = chunk_sum if sum_probs is None else sum_probs + chunk_sum

            fake_probs_all.extend(fake_probs.detach().cpu().numpy().tolist())
            count += logits.shape[0]

        if count == 0:
            return None, None, None, "No model outputs generated."

        if isinstance(sum_probs, torch.Tensor) and sum_probs.ndim == 0:
            avg_fake = float((sum_probs / count).item())
            probs_list = [round(1.0 - avg_fake, 6), round(avg_fake, 6)]
        else:
            avg_probs = (sum_probs / count).detach().cpu().numpy()
            probs_list = [round(float(p), 6) for p in avg_probs.tolist()]
            avg_fake = float(probs_list[min(MODEL_FAKE_INDEX, len(probs_list) - 1)])

        frame_probs = [round(float(p), 6) for p in fake_probs_all]
        return avg_fake, probs_list, frame_probs, None
    except Exception as e:
        return None, None, None, str(e)


def _predict_video_model_stream(
    video_path: str,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> Tuple[Optional[float], Optional[list], Optional[list], Optional[str], Optional[int], int, float]:
    """Stream PyTorch model inference over all frames in a video."""
    model, err = _load_video_model()
    if err:
        return None, None, None, err, None, 0, 0.0

    preprocess, prep_err = _load_preprocess()
    if prep_err:
        return None, None, None, prep_err, None, 0, 0.0

    try:
        import torch
        from PIL import Image as pil_image

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None, None, None, f"Cannot open video: {video_path}", None, 0, 0.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        total_hint = total_frames if total_frames > 0 else None
        progress_every = max(PROGRESS_EVERY, 1)
        if on_progress:
            on_progress(0, total_hint)

        fake_probs_all = []
        sum_probs = None
        count = 0
        processed = 0
        face_found = 0
        batch_tensors = []
        dlib_detector, _ = _get_dlib_detector()

        def flush_batch(tensors: list) -> Optional[str]:
            nonlocal sum_probs, count
            if not tensors:
                return None
            batch = torch.stack(tensors, dim=0)
            with torch.no_grad():
                logits = model(batch)

            if logits.ndim == 1:
                logits = logits.unsqueeze(0) if logits.numel() == 2 else logits.unsqueeze(1)

            if logits.shape[-1] == 1:
                probs = torch.sigmoid(logits).squeeze(-1)
                fake_probs = probs
                chunk_sum = probs.sum()
                sum_probs = chunk_sum if sum_probs is None else sum_probs + chunk_sum
            else:
                probs = torch.softmax(logits, dim=-1)
                fake_index = MODEL_FAKE_INDEX
                if fake_index < 0 or fake_index >= probs.shape[-1]:
                    fake_index = probs.shape[-1] - 1
                fake_probs = probs[:, fake_index]
                chunk_sum = probs.sum(dim=0)
                sum_probs = chunk_sum if sum_probs is None else sum_probs + chunk_sum

            fake_probs_all.extend(fake_probs.detach().cpu().numpy().tolist())
            count += logits.shape[0]
            return None

        error = None
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            processed += 1

            crop = None
            if dlib_detector is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = dlib_detector(gray, 1)
                if len(faces):
                    face = max(
                        faces,
                        key=lambda r: max(0, (r.right() - r.left())) * max(0, (r.bottom() - r.top()))
                    )
                    height_img, width_img = frame.shape[:2]
                    x, y, size = _get_boundingbox(face, width_img, height_img)
                    crop = frame[y:y + size, x:x + size]
                    if crop.size == 0:
                        crop = None

            if crop is None:
                crop = crop_largest_face(frame, detect_faces(frame), MODEL_FACE_MARGIN)

            if crop is not None:
                face_found += 1
                source = crop
            else:
                source = frame

            rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
            image = pil_image.fromarray(rgb)
            tensor = preprocess(image)
            batch_tensors.append(tensor)

            if len(batch_tensors) >= MODEL_BATCH_SIZE:
                error = flush_batch(batch_tensors)
                batch_tensors = []
                if error:
                    break

            if on_progress and (processed % progress_every == 0 or (total_frames and processed >= total_frames)):
                on_progress(processed, total_hint)

        if error is None:
            error = flush_batch(batch_tensors)

        cap.release()

        if on_progress:
            on_progress(processed, total_hint)

        if error:
            return None, None, None, error, total_hint, processed, (face_found / processed) if processed else 0.0

        if count == 0:
            return None, None, None, "No model outputs generated.", total_hint, processed, (face_found / processed) if processed else 0.0

        if isinstance(sum_probs, torch.Tensor) and sum_probs.ndim == 0:
            avg_fake = float((sum_probs / count).item())
            probs_list = [round(1.0 - avg_fake, 6), round(avg_fake, 6)]
        else:
            avg_probs = (sum_probs / count).detach().cpu().numpy()
            probs_list = [round(float(p), 6) for p in avg_probs.tolist()]
            avg_fake = float(probs_list[min(MODEL_FAKE_INDEX, len(probs_list) - 1)])

        frame_probs = [round(float(p), 6) for p in fake_probs_all]
        return avg_fake, probs_list, frame_probs, None, total_hint, processed, (face_found / processed) if processed else 0.0
    except Exception as e:
        return None, None, None, str(e), None, 0, 0.0


def detect_faces(frame: np.ndarray) -> list:
    """Detect faces in a frame using Haar cascades."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in faces]


def crop_largest_face(frame: np.ndarray, faces: list, margin: float = 0.2) -> Optional[np.ndarray]:
    """Crop the largest detected face with optional margin."""
    if not faces:
        return None

    best = max(faces, key=lambda f: f["w"] * f["h"])
    x, y, w, h = best["x"], best["y"], best["w"], best["h"]

    pad_w = int(w * margin / 2)
    pad_h = int(h * margin / 2)

    x1 = max(x - pad_w, 0)
    y1 = max(y - pad_h, 0)
    x2 = min(x + w + pad_w, frame.shape[1])
    y2 = min(y + h + pad_h, frame.shape[0])

    if x2 <= x1 or y2 <= y1:
        return None

    crop = frame[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def _compute_model_weight(face_coverage: float) -> float:
    """Determine model weight based on face coverage in sampled frames."""
    if face_coverage >= FACE_COVERAGE_THRESHOLD:
        return FUSION_MODEL_WEIGHT_STRONG
    if face_coverage <= FACE_COVERAGE_MIN:
        return FUSION_MODEL_WEIGHT_WEAK
    # Linear interpolation between weak and strong weights.
    span = max(FACE_COVERAGE_THRESHOLD - FACE_COVERAGE_MIN, 1e-6)
    t = (face_coverage - FACE_COVERAGE_MIN) / span
    return FUSION_MODEL_WEIGHT_WEAK + t * (FUSION_MODEL_WEIGHT_STRONG - FUSION_MODEL_WEIGHT_WEAK)


def _get_dlib_detector():
    """Lazily initialize dlib face detector if available."""
    global _DLIB_DETECTOR, _DLIB_ERROR
    if _DLIB_DETECTOR is not None or _DLIB_ERROR is not None:
        return _DLIB_DETECTOR, _DLIB_ERROR
    try:
        import dlib
        _DLIB_DETECTOR = dlib.get_frontal_face_detector()
        return _DLIB_DETECTOR, None
    except Exception as e:
        _DLIB_ERROR = str(e)
        return None, _DLIB_ERROR


def _get_boundingbox(face, width: int, height: int, scale: float = 1.3, minsize: Optional[int] = None):
    """Reference bounding box generator (quadratic, scaled)."""
    x1 = face.left()
    y1 = face.top()
    x2 = face.right()
    y2 = face.bottom()
    size_bb = int(max(x2 - x1, y2 - y1) * scale)
    if minsize and size_bb < minsize:
        size_bb = minsize
    center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
    x1 = max(int(center_x - size_bb // 2), 0)
    y1 = max(int(center_y - size_bb // 2), 0)
    size_bb = min(width - x1, size_bb)
    size_bb = min(height - y1, size_bb)
    return x1, y1, size_bb


def analyze_frame(frame: np.ndarray) -> dict:
    """Analyze a single frame for deepfake artifacts."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Laplacian variance (blur detection)
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Edge density
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.mean(edges) / 255.0)

    # Color histogram uniformity
    hist_scores = []
    for ch in range(3):
        hist = cv2.calcHist([frame], [ch], None, [256], [0, 256])
        hist = hist / hist.sum()
        entropy = -float(np.sum(hist[hist > 0] * np.log2(hist[hist > 0])))
        hist_scores.append(entropy)
    avg_entropy = float(np.mean(hist_scores))

    # Face artifacts
    faces = detect_faces(frame)
    face_score = 0.0
    if faces:
        for face in faces:
            x, y, w, h = face["x"], face["y"], face["w"], face["h"]
            face_roi = gray[y:y+h, x:x+w]
            if face_roi.size > 0:
                face_blur = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())
                # Lower blur variance in face compared to background = suspicious
                bg_blur = laplacian_var
                if bg_blur > 0:
                    ratio = face_blur / bg_blur
                    face_score = max(1.0 - ratio, 0) * 0.5

    # Combine signals
    blur_score = min(1.0 / (laplacian_var / 100.0 + 1.0), 1.0)
    frame_score = (blur_score * 0.3 + (1.0 - edge_density) * 0.2 +
                   (1.0 - avg_entropy / 8.0) * 0.2 + face_score * 0.3)
    frame_score = min(max(frame_score, 0), 1)

    return {
        "score": round(frame_score, 4),
        "laplacian_var": round(laplacian_var, 2),
        "edge_density": round(edge_density, 4),
        "avg_entropy": round(avg_entropy, 3),
        "face_count": len(faces),
        "faces": faces,
    }


def temporal_consistency(frame_results: list) -> dict:
    """Analyze temporal consistency across frames."""
    if len(frame_results) < 2:
        return {"temporal_score": 0.0, "inconsistencies": []}

    scores = [r["analysis"]["score"] for r in frame_results]
    face_counts = [r["analysis"]["face_count"] for r in frame_results]
    blur_values = [r["analysis"]["laplacian_var"] for r in frame_results]

    # Score variance across frames
    score_std = float(np.std(scores))
    face_count_std = float(np.std(face_counts))
    blur_std = float(np.std(blur_values))

    inconsistencies = []

    if score_std > 0.15:
        inconsistencies.append({
            "type": "score_variance",
            "title": "Frame Score Instability",
            "description": f"High variance in per-frame manipulation scores (σ={score_std:.3f}). "
                          "Authentic videos maintain consistent scores.",
            "severity": "high",
        })

    if face_count_std > 0.5:
        inconsistencies.append({
            "type": "face_flicker",
            "title": "Face Detection Instability",
            "description": f"Inconsistent face detection across frames (σ={face_count_std:.2f}). "
                          "May indicate face swapping artifacts.",
            "severity": "medium",
        })

    if blur_std > 200:
        inconsistencies.append({
            "type": "blur_variance",
            "title": "Blur Inconsistency",
            "description": f"Significant blur variations across frames (σ={blur_std:.1f}). "
                          "May indicate splicing or compositing.",
            "severity": "medium",
        })

    # Temporal score: higher = more suspicious
    temporal_score = min(
        (score_std / 0.3) * 0.4 + (face_count_std / 2.0) * 0.3 + (blur_std / 500.0) * 0.3,
        1.0
    )

    return {
        "temporal_score": round(temporal_score, 4),
        "score_std": round(score_std, 4),
        "face_count_std": round(face_count_std, 4),
        "blur_std": round(blur_std, 2),
        "inconsistencies": inconsistencies,
    }


def detect_video(
    video_path: str,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> dict:
    """Full video detection pipeline."""
    process_all = PROCESS_ALL_FRAMES
    frames = []

    if not process_all:
        frames = extract_uniform_frames(video_path, MODEL_NUM_FRAMES)
        if not frames:
            return {
                "overall_score": 0.0,
                "verdict": "ERROR",
                "evidence": [{"type": "error", "title": "No frames extracted", "severity": "high"}],
            }

    if _use_keras_backend():
        # Keras model only
        if process_all:
            (
                model_score,
                model_probs,
                model_frame_probs,
                model_error,
                total_frames,
                processed,
                face_coverage,
            ) = _predict_keras_stream(video_path, on_progress)
        else:
            if on_progress:
                on_progress(len(frames), len(frames))
            model_frames = []
            dlib_detector, _ = _get_dlib_detector()
            face_found = 0
            for f in frames:
                crop = None
                if dlib_detector is not None:
                    gray = cv2.cvtColor(f["frame"], cv2.COLOR_BGR2GRAY)
                    faces = dlib_detector(gray, 1)
                    if len(faces):
                        face = max(
                            faces,
                            key=lambda r: max(0, (r.right() - r.left())) * max(0, (r.bottom() - r.top()))
                        )
                        height, width = f["frame"].shape[:2]
                        x, y, size = _get_boundingbox(face, width, height)
                        crop = f["frame"][y:y + size, x:x + size]
                        if crop.size == 0:
                            crop = None

                if crop is None:
                    crop = crop_largest_face(f["frame"], detect_faces(f["frame"]), MODEL_FACE_MARGIN)

                if crop is not None:
                    model_frames.append(crop)
                    face_found += 1
                else:
                    model_frames.append(f["frame"])

            face_coverage = face_found / len(frames) if frames else 0.0
            total_frames = len(frames)
            processed = len(frames)
            model_score, model_probs, model_frame_probs, model_error = _predict_keras_model(model_frames)

        if model_error and MODEL_STRICT:
            return {
                "overall_score": 0.0,
                "verdict": "ERROR",
                "evidence": [{
                    "type": "model_error",
                    "title": "Model Inference Failed",
                    "description": model_error,
                    "severity": "high",
                }],
            }

        overall = round(min(max(model_score or 0.0, 0), 1), 4)

        if overall > VERDICT_MANIPULATED:
            verdict = "MANIPULATED"
        elif overall > VERDICT_SUSPICIOUS:
            verdict = "SUSPICIOUS"
        else:
            verdict = "AUTHENTIC"

        evidence = []
        if model_error:
            evidence.append({
                "type": "model_error",
                "title": "Model Inference Failed",
                "description": model_error,
                "severity": "high",
            })
        else:
            confidence = "high" if overall > 0.65 else "medium" if overall > 0.35 else "low"
            evidence.append({
                "type": "model_score",
                "title": "ML Model Confidence",
                "description": f"Model manipulation probability: {overall:.2f} (confidence: {confidence}).",
                "severity": "high" if overall > 0.65 else "medium" if overall > 0.35 else "low",
            })

        return {
            "overall_score": overall,
            "verdict": verdict,
            "avg_frame_score": None,
            "temporal_score": None,
            "heuristic_score": None,
            "model_score": round(model_score, 4) if model_score is not None else None,
            "model_probs": model_probs,
            "model_fake_index": MODEL_FAKE_INDEX,
            "model_frames": processed,
            "model_weight": None,
            "face_coverage": round(face_coverage or 0.0, 4),
            "model_frame_scores": model_frame_probs,
            "frames_analyzed": processed,
            "frame_scores": [],
            "evidence": evidence,
            "frames_total": total_frames,
        }

    # Prepare model inputs
    model_frames = []
    face_found = 0
    dlib_detector, dlib_error = _get_dlib_detector()

    if REFERENCE_ONLY:
        if process_all:
            (
                model_score,
                model_probs,
                model_frame_probs,
                model_error,
                total_frames,
                processed,
                face_coverage,
            ) = _predict_video_model_stream(video_path, on_progress)
        else:
            if on_progress:
                on_progress(len(frames), len(frames))
            for f in frames:
                crop = None
                if dlib_detector is not None:
                    gray = cv2.cvtColor(f["frame"], cv2.COLOR_BGR2GRAY)
                    faces = dlib_detector(gray, 1)
                    if len(faces):
                        face = max(
                            faces,
                            key=lambda r: max(0, (r.right() - r.left())) * max(0, (r.bottom() - r.top()))
                        )
                        height, width = f["frame"].shape[:2]
                        x, y, size = _get_boundingbox(face, width, height)
                        crop = f["frame"][y:y + size, x:x + size]
                        if crop.size == 0:
                            crop = None

                if crop is None:
                    crop = crop_largest_face(f["frame"], detect_faces(f["frame"]), MODEL_FACE_MARGIN)

                if crop is not None:
                    model_frames.append(crop)
                    face_found += 1
                else:
                    model_frames.append(f["frame"])

            face_coverage = face_found / len(frames) if frames else 0.0
            total_frames = len(frames)
            processed = len(frames)
            model_score, model_probs, model_frame_probs, model_error = _predict_video_model(model_frames)

        if model_error and MODEL_STRICT:
            return {
                "overall_score": 0.0,
                "verdict": "ERROR",
                "evidence": [{
                    "type": "model_error",
                    "title": "Model Inference Failed",
                    "description": model_error,
                    "severity": "high",
                }],
            }

        overall = round(min(max(model_score or 0.0, 0), 1), 4)

        if overall > VERDICT_MANIPULATED:
            verdict = "MANIPULATED"
        elif overall > VERDICT_SUSPICIOUS:
            verdict = "SUSPICIOUS"
        else:
            verdict = "AUTHENTIC"

        evidence = []
        if model_error:
            evidence.append({
                "type": "model_error",
                "title": "Model Inference Failed",
                "description": model_error,
                "severity": "high",
            })
        if dlib_error:
            evidence.append({
                "type": "face_detector",
                "title": "Dlib Not Available",
                "description": f"Using fallback face detector. Dlib error: {dlib_error}",
                "severity": "low",
            })
        if _TORCH_MODEL_WARN:
            evidence.append({
                "type": "model_warning",
                "title": "Model Load Warning",
                "description": _TORCH_MODEL_WARN,
                "severity": "low",
            })
        if model_score is not None:
            confidence = "high" if model_score > 0.65 else "medium" if model_score > 0.35 else "low"
            evidence.append({
                "type": "model_score",
                "title": "ML Model Confidence",
                "description": f"Model manipulation probability: {model_score:.2f} (confidence: {confidence}).",
                "severity": "high" if model_score > 0.65 else "medium" if model_score > 0.35 else "low",
            })

        return {
            "overall_score": overall,
            "verdict": verdict,
            "avg_frame_score": None,
            "temporal_score": None,
            "heuristic_score": None,
            "model_score": round(model_score, 4) if model_score is not None else None,
            "model_probs": model_probs,
            "model_fake_index": MODEL_FAKE_INDEX,
            "model_frames": processed,
            "model_weight": None,
            "face_coverage": round(face_coverage or 0.0, 4),
            "model_frame_scores": model_frame_probs,
            "frames_analyzed": processed,
            "frame_scores": [],
            "evidence": evidence,
            "frames_total": total_frames,
        }

    # Full pipeline (heuristics + fusion)
    if process_all:
        frames = extract_all_frames(video_path, on_progress)
    else:
        if not frames:
            frames = extract_uniform_frames(video_path, MODEL_NUM_FRAMES)
        if on_progress:
            on_progress(len(frames), len(frames))

    if not frames:
        return {
            "overall_score": 0.0,
            "verdict": "ERROR",
            "evidence": [{"type": "error", "title": "No frames extracted", "severity": "high"}],
        }

    frame_results = []
    for f in frames:
        analysis = analyze_frame(f["frame"])
        frame_results.append({"index": f["index"], "analysis": analysis})
        crop = None
        if dlib_detector is not None:
            gray = cv2.cvtColor(f["frame"], cv2.COLOR_BGR2GRAY)
            faces = dlib_detector(gray, 1)
            if len(faces):
                face = max(
                    faces,
                    key=lambda r: max(0, (r.right() - r.left())) * max(0, (r.bottom() - r.top()))
                )
                height, width = f["frame"].shape[:2]
                x, y, size = _get_boundingbox(face, width, height)
                crop = f["frame"][y:y + size, x:x + size]
                if crop.size == 0:
                    crop = None

        if crop is None:
            crop = crop_largest_face(f["frame"], analysis.get("faces", []), MODEL_FACE_MARGIN)

        if crop is not None:
            model_frames.append(crop)
            face_found += 1
        else:
            model_frames.append(f["frame"])

    face_coverage = face_found / len(frames) if frames else 0.0

    temporal = temporal_consistency(frame_results)
    frame_scores = [r["analysis"]["score"] for r in frame_results]
    avg_frame_score = float(np.mean(frame_scores))

    heuristic_overall = avg_frame_score * 0.6 + temporal["temporal_score"] * 0.4
    heuristic_overall = round(min(max(heuristic_overall, 0), 1), 4)

    model_score, model_probs, model_frame_probs, model_error = _predict_video_model(model_frames)

    if model_error and MODEL_STRICT:
        return {
            "overall_score": 0.0,
            "verdict": "ERROR",
            "evidence": [{
                "type": "model_error",
                "title": "Model Inference Failed",
                "description": model_error,
                "severity": "high",
            }],
        }

    if model_score is not None:
        base_weight = _compute_model_weight(face_coverage)
        if HEURISTIC_AGREEMENT_REF > 0:
            agreement = min(heuristic_overall / HEURISTIC_AGREEMENT_REF, 1.0)
        else:
            agreement = 1.0
        model_weight = base_weight * (MODEL_WEIGHT_MIN_FACTOR + (1.0 - MODEL_WEIGHT_MIN_FACTOR) * agreement)
        overall = model_weight * model_score + (1.0 - model_weight) * heuristic_overall
        overall = round(min(max(overall, 0), 1), 4)
    else:
        model_weight = None
        overall = heuristic_overall

    if overall > VERDICT_MANIPULATED:
        verdict = "MANIPULATED"
    elif overall > VERDICT_SUSPICIOUS:
        verdict = "SUSPICIOUS"
    else:
        verdict = "AUTHENTIC"

    evidence = list(temporal["inconsistencies"])

    if model_error:
        evidence.append({
            "type": "model_error",
            "title": "Model Inference Failed",
            "description": model_error,
            "severity": "high",
        })
    if dlib_error:
        evidence.append({
            "type": "face_detector",
            "title": "Dlib Not Available",
            "description": f"Using fallback face detector. Dlib error: {dlib_error}",
            "severity": "low",
        })
    if _TORCH_MODEL_WARN:
        evidence.append({
            "type": "model_warning",
            "title": "Model Load Warning",
            "description": _TORCH_MODEL_WARN,
            "severity": "low",
        })
    if model_score is not None:
        if face_coverage < FACE_COVERAGE_THRESHOLD:
            evidence.append({
                "type": "face_coverage",
                "title": "Low Face Coverage",
                "description": f"Faces detected in {face_found}/{len(frames)} sampled frames "
                               f"({face_coverage:.0%}). Model confidence may be less reliable.",
                "severity": "medium" if face_coverage >= FACE_COVERAGE_MIN else "high",
            })
        confidence = "high" if model_score > 0.65 else "medium" if model_score > 0.35 else "low"
        evidence.append({
            "type": "model_score",
            "title": "ML Model Confidence",
            "description": f"Model manipulation probability: {model_score:.2f} (confidence: {confidence}).",
            "severity": "high" if model_score > 0.65 else "medium" if model_score > 0.35 else "low",
        })
        if model_weight is not None and model_weight < base_weight:
            evidence.append({
                "type": "fusion",
                "title": "Model Weight Reduced",
                "description": f"Model weight reduced to {model_weight:.2f} due to low heuristic agreement.",
                "severity": "low",
            })
        elif model_weight is not None and model_weight < 0.8:
            evidence.append({
                "type": "fusion",
                "title": "Model-Heuristic Fusion",
                "description": f"Model weight {model_weight:.2f} based on face coverage.",
                "severity": "low",
            })
    if avg_frame_score > 0.4:
        evidence.append({
            "type": "frame_analysis",
            "title": "Frame-Level Artifacts Detected",
            "description": f"Average frame manipulation score: {avg_frame_score:.2f}. "
                          f"{len(frames)} frames analyzed.",
            "severity": "high" if avg_frame_score > 0.6 else "medium",
        })

    return {
        "overall_score": overall,
        "verdict": verdict,
        "avg_frame_score": round(avg_frame_score, 4),
        "temporal_score": temporal["temporal_score"],
        "heuristic_score": heuristic_overall,
        "model_score": round(model_score, 4) if model_score is not None else None,
        "model_probs": model_probs,
        "model_fake_index": MODEL_FAKE_INDEX,
        "model_frames": len(frames),
        "model_weight": round(model_weight, 4) if model_weight is not None else None,
        "face_coverage": round(face_coverage, 4),
        "model_frame_scores": model_frame_probs,
        "frames_analyzed": len(frames),
        "frame_scores": [round(s, 3) for s in frame_scores],
        "evidence": evidence,
        "frames_total": len(frames),
    }
