"""
Query Generation Module
Converts extracted claims into search queries for fact-checking.
"""

import re


def generate_queries(claims: list) -> list:
    """
    Generate search queries from extracted claims.

    For each claim, generates 1-2 queries by:
    - Extracting key noun phrases and entities
    - Removing filler words
    - Creating search-optimized strings

    Returns list of query dicts with claim_index and query text.
    """
    queries = []

    for i, claim in enumerate(claims):
        claim_text = claim.get("text", "")
        if not claim_text:
            continue

        # Generate primary query
        primary = _extract_key_terms(claim_text)
        if primary:
            queries.append({
                "claim_index": i,
                "claim_text": claim_text,
                "query": primary,
                "type": "primary",
            })

        # Generate secondary query (broader)
        secondary = _generate_broader_query(claim_text)
        if secondary and secondary != primary:
            queries.append({
                "claim_index": i,
                "claim_text": claim_text,
                "query": secondary,
                "type": "secondary",
            })

    return queries


def _extract_key_terms(text: str) -> str:
    """Extract key terms from a claim for an optimized search query."""
    # Remove common filler words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "that", "this", "these", "those",
        "it", "its", "they", "their", "them", "he", "she", "him",
        "her", "his", "we", "our", "us", "and", "but", "or", "not",
        "if", "then", "so", "very", "just", "also", "all", "each",
        "every", "both", "few", "more", "most", "other", "some",
    }

    # Remove punctuation
    text_clean = re.sub(r'[^\w\s]', '', text)
    words = text_clean.split()

    # Keep important words (non stop words, or capitalized, or numbers)
    key_words = []
    for word in words:
        w_lower = word.lower()
        if w_lower not in stop_words or word[0].isupper() or word.isdigit():
            key_words.append(word)

    # Limit query length
    query = " ".join(key_words[:8])
    return query.strip() if query.strip() else None


def _generate_broader_query(text: str) -> str:
    """
    Generate a broader query focusing on the main topic.
    Uses named entities and key nouns.
    """
    # Extract capitalized phrases (likely named entities)
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', text)

    # Extract key action words
    action_words = []
    important_verbs = [
        "ban", "bans", "banned", "approve", "approved", "launch",
        "launched", "confirm", "confirmed", "announce", "announced",
        "discover", "discovered", "arrest", "arrested", "kill",
        "killed", "pass", "passed", "sign", "signed",
    ]
    for word in text.lower().split():
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word in important_verbs:
            action_words.append(clean_word)

    # Combine entities and action words
    parts = entities[:3] + action_words[:2]
    if not parts:
        return None

    query = " ".join(parts) + " news"
    return query.strip()
