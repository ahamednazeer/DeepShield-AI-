"""
Claim Extraction Module
Extracts verifiable factual claims from text using rule-based NLP.
"""

import re


def extract_claims(clean_text: str, sentences: list, original_sentences: list | None = None) -> list:
    """
    Extract verifiable claims from text.

    Strategy:
    - Filter sentences that contain factual assertions
    - Look for named entity patterns, verbs of assertion, numbers/dates
    - Skip opinions, questions, and vague statements

    Returns list of claim dicts with text, type, and confidence.
    """
    if not sentences:
        return []

    claims = []
    seen = set()

    original_sentences = original_sentences or sentences

    for idx, sentence in enumerate(sentences):
        original_sentence = original_sentences[idx] if idx < len(original_sentences) else sentence
        claim = _evaluate_sentence(original_sentence, normalized_sentence=sentence)
        if claim and claim["text"] not in seen:
            seen.add(claim["text"])
            claims.append(claim)

    # If no claims extracted but text exists, use the full text as a single claim
    if not claims and clean_text:
        claims.append({
            "text": clean_text[:300],
            "type": "general",
            "confidence": 0.5,
            "original": (original_sentences[0][:300] if original_sentences else clean_text[:300]),
        })

    return claims[:10]  # Limit to 10 claims


def _evaluate_sentence(sentence: str, normalized_sentence: str | None = None) -> dict | None:
    """
    Evaluate whether a sentence contains a verifiable claim.
    Returns a claim dict or None.
    """
    # Skip very short or very long sentences
    normalized_sentence = normalized_sentence or sentence.lower()
    words = normalized_sentence.split()
    if len(words) < 4 or len(words) > 60:
        return None

    # Skip questions
    if sentence.strip().endswith("?"):
        return None

    # Skip obvious opinions
    opinion_starters = [
        "i think", "i believe", "in my opinion", "i feel",
        "it seems", "probably", "maybe", "perhaps",
    ]
    lower = normalized_sentence.lower().strip()
    if any(lower.startswith(o) for o in opinion_starters):
        return None

    # Score the sentence based on claim indicators
    score = 0.0
    claim_type = "general"

    # Named entities (capitalized words that aren't sentence starters)
    caps_pattern = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', sentence)
    if caps_pattern:
        score += 0.2
        claim_type = "entity"

    # Assertion verbs
    assertion_verbs = [
        "confirmed", "announced", "declared", "stated", "revealed",
        "reported", "claimed", "said", "banned", "approved", "rejected",
        "launched", "discovered", "invented", "created", "signed",
        "passed", "enacted", "arrested", "convicted", "killed",
    ]
    if any(verb in lower for verb in assertion_verbs):
        score += 0.3
        claim_type = "assertion"

    # Numbers / dates / statistics
    if re.search(r'\d+', sentence):
        score += 0.15
        if claim_type == "general":
            claim_type = "statistical"

    # Historical fragments still count as factual claims even without a verb.
    if re.search(r'\b(?:bce|bc|ce|ad)\b', lower) or re.search(r'\b(?:ancient|oldest|civilization)\b', lower):
        score += 0.2
        if claim_type == "general":
            claim_type = "historical"

    # Organization / country names in common patterns
    org_patterns = [
        r'\b(?:NASA|WHO|UN|FBI|CIA|EU|NATO|CDC|FDA)\b',
        r'\b(?:India|China|Russia|America|USA|UK|Japan|Germany|France)\b',
        r'\b(?:government|president|minister|court|parliament|senate)\b',
    ]
    for pattern in org_patterns:
        if re.search(pattern, sentence, re.IGNORECASE):
            score += 0.15
            if claim_type == "general":
                claim_type = "institutional"
            break

    # Scientific / health claims
    science_terms = [
        "study", "research", "scientists", "discovered", "cure",
        "vaccine", "treatment", "experiment", "evidence", "proven",
    ]
    if any(term in lower for term in science_terms):
        score += 0.2
        claim_type = "scientific"

    # Threshold
    if score < 0.2:
        return None

    return {
        "text": normalized_sentence.strip(),
        "type": claim_type,
        "confidence": round(min(score, 1.0), 3),
        "original": sentence.strip(),
    }
