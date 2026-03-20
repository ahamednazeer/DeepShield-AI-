"""
Audio Deepfake Detection Pipeline
Analyzes spectrograms, MFCCs, pitch dynamics, and spectral features
to detect voice cloning and audio manipulation.
"""

import numpy as np
import librosa


def extract_audio_features(audio_path: str) -> dict:
    """Extract spectral and temporal features from audio."""
    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=30)
    except Exception as e:
        return {"error": str(e)}

    if len(y) < sr:  # Less than 1 second
        return {"error": "Audio too short for analysis"}

    # MFCCs
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfccs, axis=1).tolist()
    mfcc_std = np.std(mfccs, axis=1).tolist()

    # Spectral features
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]

    # Zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(y)[0]

    # Chroma features
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)

    # Pitch
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_values = []
    for t in range(pitches.shape[1]):
        index = magnitudes[:, t].argmax()
        pitch = pitches[index, t]
        if pitch > 0:
            pitch_values.append(float(pitch))

    return {
        "duration": float(len(y) / sr),
        "sample_rate": sr,
        "mfcc_mean": [round(m, 3) for m in mfcc_mean],
        "mfcc_std": [round(s, 3) for s in mfcc_std],
        "spectral_centroid_mean": round(float(np.mean(spectral_centroid)), 2),
        "spectral_centroid_std": round(float(np.std(spectral_centroid)), 2),
        "spectral_bandwidth_mean": round(float(np.mean(spectral_bandwidth)), 2),
        "spectral_rolloff_mean": round(float(np.mean(spectral_rolloff)), 2),
        "zcr_mean": round(float(np.mean(zcr)), 5),
        "zcr_std": round(float(np.std(zcr)), 5),
        "chroma_mean": [round(float(c), 3) for c in np.mean(chroma, axis=1)],
        "pitch_mean": round(float(np.mean(pitch_values)), 2) if pitch_values else 0,
        "pitch_std": round(float(np.std(pitch_values)), 2) if pitch_values else 0,
        "pitch_range": round(float(np.ptp(pitch_values)), 2) if pitch_values else 0,
    }


def analyze_spectral_anomalies(features: dict) -> dict:
    """Detect spectral anomalies indicative of voice synthesis."""
    score = 0.0
    anomalies = []

    # MFCC variance — synthesized audio tends to have lower MFCC variance
    mfcc_stds = features.get("mfcc_std", [])
    if mfcc_stds:
        avg_mfcc_std = float(np.mean(mfcc_stds))
        if avg_mfcc_std < 8.0:
            score += 0.25
            anomalies.append({
                "type": "low_mfcc_variance",
                "title": "Low MFCC Variance",
                "description": f"MFCC standard deviation ({avg_mfcc_std:.2f}) is unusually low. "
                              "Voice cloning systems often produce uniform spectral characteristics.",
                "severity": "medium",
            })

    # Spectral centroid stability — TTS tends to be too consistent
    centroid_std = features.get("spectral_centroid_std", 0)
    if centroid_std < 300:
        score += 0.2
        anomalies.append({
            "type": "stable_centroid",
            "title": "Abnormally Stable Spectral Centroid",
            "description": f"Spectral centroid variation ({centroid_std:.1f} Hz) is very low. "
                          "Natural speech has more spectral variation.",
            "severity": "medium",
        })

    # Zero-crossing rate anomaly
    zcr_std = features.get("zcr_std", 0)
    if zcr_std < 0.01:
        score += 0.15
        anomalies.append({
            "type": "zcr_anomaly",
            "title": "Zero-Crossing Rate Anomaly",
            "description": f"Very low ZCR variation ({zcr_std:.5f}). "
                          "May indicate synthetic waveform regularity.",
            "severity": "low",
        })

    # Pitch dynamics
    pitch_std = features.get("pitch_std", 0)
    pitch_range = features.get("pitch_range", 0)
    if pitch_std > 0 and pitch_std < 30:
        score += 0.2
        anomalies.append({
            "type": "flat_pitch",
            "title": "Flat Pitch Contour",
            "description": f"Pitch variation is too narrow (σ={pitch_std:.1f} Hz, range={pitch_range:.1f} Hz). "
                          "Natural speech has wider pitch dynamics.",
            "severity": "medium",
        })

    # Chroma uniformity
    chroma_mean = features.get("chroma_mean", [])
    if chroma_mean:
        chroma_std = float(np.std(chroma_mean))
        if chroma_std < 0.05:
            score += 0.15
            anomalies.append({
                "type": "chroma_uniformity",
                "title": "Uniform Chroma Distribution",
                "description": f"Chroma features are unusually uniform (σ={chroma_std:.4f}). "
                              "May indicate generated audio.",
                "severity": "low",
            })

    return {
        "spectral_score": round(min(score, 1.0), 4),
        "anomalies": anomalies,
    }


def detect_audio(audio_path: str) -> dict:
    """Full audio detection pipeline."""
    features = extract_audio_features(audio_path)

    if "error" in features:
        return {
            "overall_score": 0.0,
            "verdict": "ERROR",
            "evidence": [{"type": "error", "title": f"Audio analysis error: {features['error']}", "severity": "high"}],
        }

    spectral = analyze_spectral_anomalies(features)

    overall = spectral["spectral_score"]

    if overall > 0.65:
        verdict = "MANIPULATED"
    elif overall > 0.35:
        verdict = "SUSPICIOUS"
    else:
        verdict = "AUTHENTIC"

    return {
        "overall_score": overall,
        "verdict": verdict,
        "features": features,
        "evidence": spectral["anomalies"],
    }
