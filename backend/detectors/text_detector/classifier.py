"""
Fake News Classification Module
Uses a Logistic Regression classifier with TF-IDF features.
Falls back to heuristic-based scoring when no trained model is available.
"""

import os
import pickle
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
CLASSIFIER_PATH = MODEL_DIR / "fake_news_clf.pkl"
VECTORIZER_PATH = MODEL_DIR / "tfidf_vectorizer.pkl"

_classifier = None
_vectorizer = None
_is_loaded = False


def _load_model():
    """Load the trained classifier and vectorizer if available."""
    global _classifier, _vectorizer, _is_loaded

    if _is_loaded:
        return

    _is_loaded = True

    if CLASSIFIER_PATH.exists() and VECTORIZER_PATH.exists():
        try:
            with open(CLASSIFIER_PATH, "rb") as f:
                _classifier = pickle.load(f)
            with open(VECTORIZER_PATH, "rb") as f:
                _vectorizer = pickle.load(f)
        except Exception as e:
            print(f"[TextDetector] Failed to load classifier: {e}")
            _classifier = None
            _vectorizer = None


def classify_text(clean_text: str, features: dict) -> dict:
    """
    Classify text as fake or real.

    Uses trained ML model if available, otherwise falls back to
    heuristic-based classification using stylistic features.

    Returns:
        dict with fake_probability (0-1), classification, signals, method
    """
    _load_model()

    if _classifier is not None and _vectorizer is not None:
        return _classify_with_model(clean_text)
    else:
        return _classify_heuristic(clean_text, features)


def _classify_with_model(clean_text: str) -> dict:
    """Classify using the trained ML model."""
    try:
        vector = _vectorizer.transform([clean_text])
        proba = _classifier.predict_proba(vector)[0]

        # Assuming class 1 = fake, class 0 = real
        fake_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])

        return {
            "fake_probability": round(fake_prob, 4),
            "classification": "FAKE" if fake_prob > 0.5 else "REAL",
            "confidence": round(abs(fake_prob - 0.5) * 2, 4),
            "method": "ml_model",
            "signals": [],
        }
    except Exception as e:
        print(f"[TextDetector] ML classification failed: {e}")
        return _classify_heuristic(clean_text, {"stylistic": {}})


def _classify_heuristic(clean_text: str, features: dict) -> dict:
    """
    Heuristic-based classification using stylistic signals.
    Used when no trained model is available.
    """
    stylistic = features.get("stylistic", {})
    signals = stylistic.get("signals", [])

    score = 0.3  # Base neutral score

    # Sensational language
    sensational_ratio = stylistic.get("sensational_ratio", 0)
    if sensational_ratio > 0.1:
        score += 0.25
    elif sensational_ratio > 0.05:
        score += 0.15
    elif sensational_ratio > 0:
        score += 0.08

    # Emotional language
    emotional_ratio = stylistic.get("emotional_ratio", 0)
    if emotional_ratio > 0.1:
        score += 0.15
    elif emotional_ratio > 0.05:
        score += 0.08
    elif emotional_ratio > 0:
        score += 0.04

    # Misleading phrases
    if stylistic.get("has_misleading_phrases", False):
        score += 0.2

    # ALL CAPS check
    words = clean_text.split()
    caps_words = sum(1 for w in clean_text.split() if w.isupper() and len(w) > 2)
    if caps_words > 3:
        score += 0.1
        signals.append({
            "type": "excessive_caps",
            "severity": "medium",
            "detail": f"Found {caps_words} ALL-CAPS words",
        })

    # Very short text (could be clickbait headline)
    word_count = stylistic.get("word_count", len(words))
    if word_count < 15:
        score += 0.05
        signals.append({
            "type": "short_text",
            "severity": "low",
            "detail": "Very short text, possible clickbait headline",
        })

    # Lack of specifics (no numbers, dates, named entities)
    has_numbers = any(c.isdigit() for c in clean_text)
    if not has_numbers and word_count > 20:
        score += 0.05

    # Clamp
    score = min(max(score, 0.0), 1.0)

    return {
        "fake_probability": round(score, 4),
        "classification": "FAKE" if score > 0.5 else "REAL",
        "confidence": round(abs(score - 0.5) * 2, 4),
        "method": "heuristic",
        "signals": signals,
    }


def train_and_save(texts: list, labels: list):
    """
    Train a new classifier on provided data and save to disk.

    Args:
        texts: list of text strings
        labels: list of 0 (real) or 1 (fake)
    """
    global _classifier, _vectorizer

    print(f"[TextDetector] Training on {len(texts)} samples...")

    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        stop_words="english",
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
    )

    X = vectorizer.fit_transform(texts)
    y = np.array(labels)

    clf = LogisticRegression(
        max_iter=1000,
        C=1.0,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X, y)

    # Evaluate
    accuracy = clf.score(X, y)
    print(f"[TextDetector] Training accuracy: {accuracy:.4f}")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLASSIFIER_PATH, "wb") as f:
        pickle.dump(clf, f)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)

    _classifier = clf
    _vectorizer = vectorizer

    print("[TextDetector] Model saved successfully.")
    return {"accuracy": accuracy, "samples": len(texts)}
