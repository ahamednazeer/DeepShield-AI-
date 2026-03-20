"""
Text Preprocessing Module
Cleans and standardizes input text for analysis.
"""

import re
import string


def preprocess_text(text: str) -> dict:
    """
    Clean and preprocess input text.

    Operations:
    - Lowercasing
    - Remove URLs
    - Remove extra whitespace
    - Remove special characters / noise
    - Sentence segmentation
    - Tokenization

    Returns dict with clean_text, sentences, tokens, and metadata.
    """
    original_text = text.strip()

    # Preserve a case-sensitive normalized form for NER and historical phrases.
    normalized_original = original_text
    normalized_original = re.sub(r'https?://\S+|www\.\S+', '', normalized_original)
    normalized_original = re.sub(r'\S+@\S+', '', normalized_original)
    normalized_original = re.sub(r'<[^>]+>', '', normalized_original)
    normalized_original = re.sub(r'[^\w\s.,!?;:\'()~\-]', ' ', normalized_original)
    normalized_original = re.sub(r'\s+', ' ', normalized_original).strip()

    # Lowercase
    clean = original_text.lower()

    # Remove URLs
    clean = re.sub(r'https?://\S+|www\.\S+', '', clean)

    # Remove email addresses
    clean = re.sub(r'\S+@\S+', '', clean)

    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', clean)

    # Remove special characters but keep sentence-ending punctuation
    clean = re.sub(r'[^\w\s.,!?;:\'-]', ' ', clean)

    # Remove extra whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Sentence segmentation (simple rule-based)
    sentences = _segment_sentences(clean)
    original_sentences = _segment_sentences(normalized_original)
    if len(original_sentences) != len(sentences):
        original_sentences = [normalized_original] if normalized_original else []

    # Tokenization
    tokens = _tokenize(clean)

    # Compute some text statistics
    stats = {
        "original_length": len(original_text),
        "clean_length": len(clean),
        "sentence_count": len(sentences),
        "token_count": len(tokens),
        "avg_sentence_length": round(
            sum(len(s.split()) for s in sentences) / max(len(sentences), 1), 1
        ),
        "exclamation_count": original_text.count("!"),
        "question_count": original_text.count("?"),
        "caps_ratio": _caps_ratio(original_text),
    }

    return {
        "original_text": original_text,
        "clean_text": clean,
        "sentences": sentences,
        "original_sentences": original_sentences,
        "tokens": tokens,
        "stats": stats,
    }


def _segment_sentences(text: str) -> list:
    """Split text into sentences."""
    # Split on sentence-ending punctuation followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Filter empty
    return [s.strip() for s in sentences if s.strip()]


def _tokenize(text: str) -> list:
    """Simple word tokenization."""
    # Remove punctuation for tokenization
    text_no_punct = text.translate(str.maketrans('', '', string.punctuation))
    tokens = text_no_punct.split()
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]


def _caps_ratio(text: str) -> float:
    """Calculate ratio of uppercase characters."""
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return 0.0
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    return round(upper_count / len(alpha_chars), 3)
