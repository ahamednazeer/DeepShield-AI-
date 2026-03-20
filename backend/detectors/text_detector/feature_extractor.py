"""
Feature Extraction Module
Converts text into numerical representations for classification.
Uses TF-IDF vectorization.
"""

import os
import pickle
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
VECTORIZER_PATH = MODEL_DIR / "tfidf_vectorizer.pkl"

# Global vectorizer instance
_vectorizer = None


def _get_vectorizer() -> TfidfVectorizer:
    """Get or create the TF-IDF vectorizer."""
    global _vectorizer

    if _vectorizer is not None:
        return _vectorizer

    # Try to load saved vectorizer
    if VECTORIZER_PATH.exists():
        with open(VECTORIZER_PATH, "rb") as f:
            _vectorizer = pickle.load(f)
        return _vectorizer

    # Create new vectorizer with reasonable defaults
    _vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        stop_words="english",
        min_df=1,
        max_df=0.95,
        sublinear_tf=True,
    )

    return _vectorizer


def extract_features(clean_text: str) -> dict:
    """
    Extract TF-IDF features from preprocessed text.

    Returns dict with:
    - vector: sparse TF-IDF vector (or None if vectorizer not fitted)
    - top_terms: most important terms
    - feature_stats: statistics about the features
    """
    vectorizer = _get_vectorizer()

    try:
        # Try to transform (works if vectorizer is already fitted)
        vector = vectorizer.transform([clean_text])
        top_terms = _get_top_terms(vector, vectorizer, top_n=10)
    except Exception:
        # Vectorizer not fitted yet — return empty features
        # The classifier will handle this case
        vector = None
        top_terms = []

    # Extract stylistic features regardless of TF-IDF
    stylistic = _extract_stylistic_features(clean_text)

    return {
        "vector": vector,
        "top_terms": top_terms,
        "stylistic": stylistic,
    }


def _get_top_terms(vector, vectorizer, top_n=10) -> list:
    """Get the most important TF-IDF terms."""
    try:
        feature_names = vectorizer.get_feature_names_out()
        sorted_indices = vector.toarray()[0].argsort()[::-1][:top_n]
        terms = []
        for idx in sorted_indices:
            score = vector.toarray()[0][idx]
            if score > 0:
                terms.append({
                    "term": feature_names[idx],
                    "score": round(float(score), 4),
                })
        return terms
    except Exception:
        return []


def _extract_stylistic_features(text: str) -> dict:
    """Extract stylistic / linguistic features that indicate fake news."""
    words = text.split()
    word_count = len(words)

    # Sensational words
    sensational_words = {
        "shocking", "breaking", "urgent", "bombshell", "explosive",
        "unbelievable", "incredible", "stunning", "horrifying", "terrifying",
        "outrageous", "scandal", "exposed", "revealed", "secret",
        "conspiracy", "banned", "destroyed", "miracle", "deadly",
        "catastrophic", "unprecedented", "controversial", "confirmed",
    }

    # Emotional words
    emotional_words = {
        "amazing", "terrible", "horrible", "wonderful", "disgusting",
        "beautiful", "ugly", "hate", "love", "fear", "angry", "furious",
        "excited", "depressed", "thrilled", "devastated", "ecstatic",
    }

    # Misleading phrases
    misleading_phrases = [
        "you won't believe", "they don't want you to know",
        "the truth about", "exposed", "what they're hiding",
        "mainstream media won't tell you", "going viral",
        "share before it's deleted", "must see", "100%",
    ]

    sensational_count = sum(1 for w in words if w.lower() in sensational_words)
    emotional_count = sum(1 for w in words if w.lower() in emotional_words)
    misleading_count = sum(
        1 for phrase in misleading_phrases
        if phrase.lower() in text.lower()
    )

    return {
        "word_count": word_count,
        "sensational_word_count": sensational_count,
        "emotional_word_count": emotional_count,
        "misleading_phrase_count": misleading_count,
        "sensational_ratio": round(sensational_count / max(word_count, 1), 4),
        "emotional_ratio": round(emotional_count / max(word_count, 1), 4),
        "has_misleading_phrases": misleading_count > 0,
        "signals": _build_signal_list(
            sensational_count, emotional_count, misleading_count
        ),
    }


def _build_signal_list(sensational, emotional, misleading) -> list:
    """Build a list of detected stylistic signals."""
    signals = []
    if sensational > 0:
        signals.append({
            "type": "sensational_tone",
            "severity": "high" if sensational > 2 else "medium",
            "detail": f"Found {sensational} sensational word(s)",
        })
    if emotional > 0:
        signals.append({
            "type": "emotional_language",
            "severity": "high" if emotional > 2 else "medium",
            "detail": f"Found {emotional} emotionally charged word(s)",
        })
    if misleading > 0:
        signals.append({
            "type": "misleading_phrasing",
            "severity": "high",
            "detail": f"Found {misleading} misleading phrase(s)",
        })
    return signals


def save_vectorizer(vectorizer: TfidfVectorizer):
    """Save a fitted vectorizer to disk."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)
