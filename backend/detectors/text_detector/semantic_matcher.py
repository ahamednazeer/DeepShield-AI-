"""
Semantic Matching Module
Compares extracted claims against retrieved evidence using text similarity.
"""

import re
import math
from collections import Counter

CANONICAL_TOKEN_MAP = {
    "stocks": "stock",
    "stock": "stock",
    "shares": "stock",
    "equities": "stock",
    "equity": "stock",
    "close": "close",
    "closed": "close",
    "closing": "close",
    "end": "close",
    "ended": "close",
    "finish": "close",
    "finished": "close",
    "lower": "lower",
    "low": "lower",
    "down": "lower",
    "fall": "lower",
    "falls": "lower",
    "fell": "lower",
    "drop": "lower",
    "drops": "lower",
    "dropped": "lower",
    "dip": "lower",
    "dips": "lower",
    "slip": "lower",
    "slips": "lower",
    "attention": "focus",
    "focus": "focus",
    "turn": "focus",
    "turns": "focus",
    "turned": "focus",
    "shift": "focus",
    "shifts": "focus",
    "shifted": "focus",
    "await": "focus",
    "awaits": "focus",
    "watch": "focus",
    "watches": "focus",
    "investors": "investor",
    "investor": "investor",
    "fed": "fed",
    "federalreserve": "fed",
}


def match_claims_to_evidence(claims: list, fact_results: dict) -> list:
    """
    Match each claim against fact-check evidence using cosine similarity.

    Determines:
    - Whether evidence supports, contradicts, or is unrelated to claims
    - Semantic similarity scores
    - Match type (exact, partial, misleading, no_match)

    Returns list of match results per claim.
    """
    results = []

    for i, claim in enumerate(claims):
        claim_text = claim.get("text", "")
        if not claim_text:
            continue

        claim_terms = _simple_tokenize(claim_text.lower())

        # Gather all evidence texts for this claim
        evidence_texts = _gather_evidence_for_claim(i, fact_results)

        if not evidence_texts:
            results.append({
                "claim_index": i,
                "claim_text": claim_text,
                "match_type": "no_evidence",
                "best_similarity": 0.0,
                "evidence_count": 0,
                "matches": [],
                "assessment": "No evidence found to verify this claim",
            })
            continue

        # Compare claim against each evidence
        matches = []

        for evidence in evidence_texts:
            best_text_match = _find_best_text_match(claim_text, claim_terms, evidence)
            match_type = _determine_match_type(
                similarity=best_text_match["similarity"],
                overlap_count=len(best_text_match["overlap_terms"]),
                claim_term_count=len(set(claim_terms)),
                relevance_score=best_text_match["relevance_score"],
                match_field=best_text_match["match_field"],
            )
            match_info = {
                "type": evidence["type"],
                "source": evidence["source"],
                "title": evidence.get("title", ""),
                "url": evidence.get("url", ""),
                "extract": evidence.get("extract", ""),
                "text": evidence["text"][:200],
                "similarity": round(best_text_match["similarity"], 4),
                "overlap_terms": best_text_match["overlap_terms"],
                "overlap_ratio": best_text_match["overlap_ratio"],
                "relevance_score": round(best_text_match["relevance_score"], 4),
                "match_field": best_text_match["match_field"],
                "match_type": match_type,
            }
            matches.append(match_info)
        best_match = max(matches, key=_match_sort_key)

        # Assessment
        assessment = _generate_assessment(best_match["match_type"])

        results.append({
            "claim_index": i,
            "claim_text": claim_text,
            "match_type": best_match["match_type"],
            "best_similarity": best_match["similarity"],
            "best_relevance": best_match["relevance_score"],
            "overlap_terms": best_match["overlap_terms"],
            "overlap_ratio": best_match["overlap_ratio"],
            "evidence_count": len(evidence_texts),
            "matches": sorted(matches, key=_match_sort_key, reverse=True)[:5],
            "assessment": assessment,
        })

    return results


def _gather_evidence_for_claim(claim_index: int, fact_results: dict) -> list:
    """Gather all evidence texts related to a specific claim."""
    evidence = []

    # News articles
    for news in fact_results.get("news_results", []):
        if news.get("claim_index") == claim_index:
            for article in news.get("articles", []):
                text = f"{article.get('title', '')} {article.get('description', '')}"
                if text.strip():
                    provider = article.get("provider")
                    source_name = article.get("source", "Unknown")
                    evidence.append({
                        "type": "news",
                        "source": f"{provider}: {source_name}" if provider else source_name,
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "extract": article.get("description", ""),
                        "text": text.strip(),
                    })

    # Wikipedia results
    for wiki in fact_results.get("wiki_results", []):
        if wiki.get("claim_index") == claim_index:
            for result in wiki.get("results", []):
                text = result.get("extract", "") or result.get("snippet", "")
                if text.strip():
                    title = result.get("title", "")
                    evidence.append({
                        "type": "wikipedia",
                        "source": "Wikipedia",
                        "title": title,
                        "url": _build_wikipedia_url(title),
                        "extract": result.get("extract", "") or result.get("snippet", ""),
                        "text": text.strip(),
                    })

    return evidence


def _cosine_similarity(text_a: str, text_b: str) -> float:
    """
    Compute cosine similarity between two texts using TF term vectors.
    Simple but effective for short text comparison.
    """
    # Tokenize and lowercase
    tokens_a = _simple_tokenize(text_a.lower())
    tokens_b = _simple_tokenize(text_b.lower())

    if not tokens_a or not tokens_b:
        return 0.0

    # Build term frequency vectors
    counter_a = Counter(tokens_a)
    counter_b = Counter(tokens_b)

    # Get all unique terms
    all_terms = set(counter_a.keys()) | set(counter_b.keys())

    # Compute dot product and magnitudes
    dot_product = sum(counter_a.get(t, 0) * counter_b.get(t, 0) for t in all_terms)
    magnitude_a = math.sqrt(sum(v ** 2 for v in counter_a.values()))
    magnitude_b = math.sqrt(sum(v ** 2 for v in counter_b.values()))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def _simple_tokenize(text: str) -> list:
    """Simple tokenization removing stop words."""
    text = re.sub(r"\bfederal\s+reserve\b", "federalreserve", text, flags=re.IGNORECASE)
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "but", "not", "it", "its", "this", "that",
        "he", "she", "they", "we", "his", "her", "their", "our",
        "has", "have", "had", "do", "does", "did", "will", "would",
        "news", "article", "articles", "report", "reported", "reports",
        "official", "officials", "latest", "update", "updates",
        "today", "yesterday", "tomorrow",
    }
    words = re.findall(r'\b\w+\b', text)
    normalized = []
    for word in words:
        token = _normalize_token(word)
        if token and token not in stop_words and len(token) > 1:
            normalized.append(token)
    return normalized


def _normalize_token(token: str) -> str:
    """Normalize inflections and common news-headline paraphrases."""
    token = token.lower().strip("'")
    if token.endswith("'s"):
        token = token[:-2]

    token = CANONICAL_TOKEN_MAP.get(token, token)

    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > 4 and token.endswith(suffix):
            candidate = token[: -len(suffix)]
            token = CANONICAL_TOKEN_MAP.get(candidate, candidate)
            break

    return CANONICAL_TOKEN_MAP.get(token, token)


def _shared_terms(text_a: str, text_b: str) -> list:
    """Return shared content tokens between the claim and the evidence."""
    terms_a = set(_simple_tokenize(text_a.lower()))
    terms_b = set(_simple_tokenize(text_b.lower()))
    return sorted(terms_a & terms_b)


def _combine_relevance(similarity: float, overlap_ratio: float) -> float:
    """
    Blend cosine similarity with claim-token coverage.
    Topical overlap alone should not count as support.
    """
    return round((similarity * 0.7) + (overlap_ratio * 0.3), 4)


def _find_best_text_match(claim_text: str, claim_terms: list, evidence: dict) -> dict:
    """Compare the claim against multiple evidence fields and keep the strongest match."""
    candidates = [
        ("title", evidence.get("title", "")),
        ("extract", evidence.get("extract", "")),
        ("combined", evidence.get("text", "")),
    ]
    best = {
        "match_field": "combined",
        "similarity": 0.0,
        "overlap_terms": [],
        "overlap_ratio": 0.0,
        "relevance_score": 0.0,
    }

    for field_name, candidate_text in candidates:
        if not candidate_text or not candidate_text.strip():
            continue

        similarity = _cosine_similarity(claim_text, candidate_text)
        overlap_terms = _shared_terms(claim_text, candidate_text)
        overlap_ratio = round(
            len(overlap_terms) / max(len(set(claim_terms)), 1), 4
        )
        relevance_score = _combine_relevance(similarity, overlap_ratio)

        if field_name == "title":
            relevance_score = min(relevance_score + 0.08, 1.0)

        candidate = {
            "match_field": field_name,
            "similarity": similarity,
            "overlap_terms": overlap_terms,
            "overlap_ratio": overlap_ratio,
            "relevance_score": relevance_score,
        }

        if _candidate_sort_key(candidate) > _candidate_sort_key(best):
            best = candidate

    return best


def _candidate_sort_key(candidate: dict) -> tuple:
    return (
        len(candidate.get("overlap_terms", [])),
        candidate.get("relevance_score", 0),
        candidate.get("similarity", 0),
    )


def _determine_match_type(
    similarity: float,
    overlap_count: int,
    claim_term_count: int,
    relevance_score: float,
    match_field: str,
) -> str:
    """Determine the type of match based on similarity score."""
    required_overlap = 1 if claim_term_count <= 2 else 2

    if overlap_count < required_overlap:
        return "no_match"
    if match_field == "title":
        if overlap_count >= 3 and relevance_score >= 0.34:
            return "strong_match"
        if overlap_count >= 2 and relevance_score >= 0.24:
            return "partial_match"
        if relevance_score >= 0.18:
            return "weak_match"
        return "no_match"
    if similarity >= 0.55 and relevance_score >= 0.5:
        return "strong_match"
    elif similarity >= 0.38 and relevance_score >= 0.35:
        return "partial_match"
    elif similarity >= 0.28 and relevance_score >= 0.28:
        return "weak_match"
    return "no_match"


def _match_rank(match_type: str) -> int:
    ranks = {
        "strong_match": 3,
        "partial_match": 2,
        "weak_match": 1,
        "no_match": 0,
    }
    return ranks.get(match_type, 0)


def _match_sort_key(match: dict) -> tuple:
    return (
        _match_rank(match.get("match_type", "no_match")),
        match.get("relevance_score", 0),
        match.get("similarity", 0),
    )


def _build_wikipedia_url(title: str) -> str:
    """Generate a stable Wikipedia URL from a page title."""
    slug = "_".join(title.split())
    return f"https://en.wikipedia.org/wiki/{slug}" if slug else ""


def _generate_assessment(match_type: str) -> str:
    """Generate a human-readable assessment of the match."""
    assessments = {
        "strong_match": "Evidence strongly supports this claim",
        "partial_match": "Evidence partially matches — claim may be misleading or exaggerated",
        "weak_match": "Only a weak topical connection was found — claim remains unverified",
        "no_match": "Retrieved results do not closely match this claim",
    }
    return assessments.get(match_type, "Unable to assess")
