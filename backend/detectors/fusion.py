"""
Multi-Modal Fusion Engine
Combines detection scores from image, video, and audio pipelines
into a final weighted trust score.
"""


def fuse_scores(
    image_score: float = None,
    video_score: float = None,
    audio_score: float = None,
    media_type: str = "image",
) -> dict:
    """
    Fuse detection scores from multiple modalities.
    For single-modality analysis, the detected modality score is used directly.
    For multi-modal (e.g., video with audio), scores are weighted.
    """
    scores = {}
    weights = {}

    if image_score is not None:
        scores["image"] = image_score
        weights["image"] = 0.5

    if video_score is not None:
        scores["video"] = video_score
        weights["video"] = 0.6

    if audio_score is not None:
        scores["audio"] = audio_score
        weights["audio"] = 0.4

    if not scores:
        return {"fused_score": 0.0, "verdict": "ERROR", "modalities": {}}

    # Normalize weights
    total_weight = sum(weights.values())
    fused_score = sum(scores[k] * weights[k] for k in scores) / total_weight
    fused_score = round(min(max(fused_score, 0), 1), 4)

    if fused_score > 0.65:
        verdict = "MANIPULATED"
    elif fused_score > 0.35:
        verdict = "SUSPICIOUS"
    else:
        verdict = "AUTHENTIC"

    return {
        "fused_score": fused_score,
        "verdict": verdict,
        "modalities": scores,
        "weights": {k: round(weights[k] / total_weight, 3) for k in weights},
    }
