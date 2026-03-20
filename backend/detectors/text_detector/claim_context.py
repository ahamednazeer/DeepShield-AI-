"""
Rule-based claim context classifier.
Determines whether a claim is breaking news, current affairs, evergreen fact,
historical, mixed, opinion, predictive, query-like, or too weak to classify.
"""

from __future__ import annotations

import re
from datetime import datetime

from .nlp_features import (
    build_nlp_view,
    contains_term,
    count_recency_markers,
    entity_signal as dynamic_entity_signal,
    has_entity_event_pattern,
    has_noncopular_verb,
    is_dynamic_copular_clause,
)

FACTUAL_TYPES = {
    "breaking_news",
    "current_affairs",
    "evergreen_fact",
    "historical_claim",
}

SPECIAL_TYPES = {
    "query_claim",
    "opinion",
    "predictive_claim",
    "unknown_signal",
    "mixed",
}

ALL_TYPES = FACTUAL_TYPES | SPECIAL_TYPES

QUESTION_PREFIXES = (
    "did ", "does ", "do ", "is ", "are ", "was ", "were ",
    "has ", "have ", "had ", "can ", "could ", "will ", "would ",
    "should ", "what ", "when ", "where ", "why ", "how ", "who ",
)

BREAKING_TERMS = {
    "breaking": 3.0,
    "just": 3.0,
    "right now": 3.0,
    "now": 2.4,
    "currently": 2.0,
    "latest": 2.6,
    "today": 3.0,
    "yesterday": 2.2,
    "this morning": 2.5,
    "this evening": 2.5,
    "tonight": 2.3,
    "live": 2.6,
    "minutes ago": 3.0,
    "hours ago": 2.8,
}

EVENT_VERBS = {
    "announce": 2.0,
    "confirm": 1.8,
    "send": 1.8,
    "quit": 2.3,
    "resign": 2.3,
    "approve": 1.8,
    "pass": 1.8,
    "arrest": 2.2,
    "launch": 1.8,
    "say": 1.6,
    "hike": 1.9,
    "boost": 1.8,
    "greenlight": 1.8,
    "escort": 1.9,
    "deploy": 2.0,
    "dispatch": 2.0,
    "move": 1.4,
    "attack": 2.4,
    "target": 1.8,
    "seize": 2.0,
    "detain": 1.8,
    "evacuate": 1.8,
    "intercept": 2.0,
    "warn": 1.6,
    "threaten": 1.8,
    "ban": 2.0,
    "rule": 1.8,
    "won": 2.2,
    "close": 1.6,
    "lose": 2.0,
    "kill": 2.7,
    "die": 2.5,
    "strike": 2.0,
    "collapse": 2.0,
    "surge": 1.8,
    "fall": 1.8,
    "rise": 1.6,
    "declare": 1.8,
    "reveal": 1.8,
    "report": 1.4,
    "sign": 1.8,
    "enact": 2.0,
    "increase": 2.0,
    "decrease": 2.0,
    "raise": 1.8,
    "cut": 1.8,
}

CURRENT_AFFAIRS_TERMS = {
    "official": 1.6,
    "security": 1.8,
    "warship": 2.4,
    "navy": 2.3,
    "naval": 2.1,
    "military": 2.2,
    "defense": 2.0,
    "defence": 2.0,
    "escort": 1.6,
    "maritime": 1.8,
    "gulf of oman": 2.4,
    "threat": 1.8,
    "iran": 2.0,
    "israel": 2.0,
    "white house": 2.2,
    "government": 2.1,
    "policy": 2.0,
    "court": 2.0,
    "parliament": 2.2,
    "senate": 2.1,
    "minister": 2.1,
    "president": 2.1,
    "prime minister": 2.4,
    "election": 2.4,
    "budget": 2.0,
    "inflation": 2.0,
    "sanctions": 2.2,
    "war": 2.3,
    "conflict": 2.0,
    "economy": 1.7,
    "central bank": 2.4,
    "repo rate": 2.5,
    "interest rate": 2.2,
    "fed": 2.5,
    "rbi": 2.5,
    "supreme court": 2.4,
    "congress": 2.0,
    "ceasefire": 2.1,
    "trade deal": 2.0,
    "tariff": 2.0,
    "startup": 1.3,
}

EVERGREEN_PATTERNS = {
    r"\bis a\b": 2.0,
    r"\bis an\b": 2.0,
    r"\bis the\b": 1.4,
    r"\bis known for\b": 2.4,
    r"\bis located in\b": 2.4,
    r"\bis one of the\b": 2.2,
    r"\bhas a\b": 1.6,
    r"\bhas an\b": 1.6,
    r"\bhas\b": 1.0,
    r"\brefers to\b": 2.0,
}

EVERGREEN_TERMS = {
    "industry": 1.5,
    "workforce": 1.8,
    "capital": 2.2,
    "language": 1.8,
    "culture": 1.6,
    "history": 1.6,
    "located": 1.8,
    "known": 1.3,
    "major film industry": 2.6,
    "largest democracy": 2.2,
    "it workforce": 2.3,
    "technology sector": 1.8,
    "oldest civilizations": 2.4,
}

HISTORICAL_TERMS = {
    "historically": 2.8,
    "formerly": 2.4,
    "in the past": 2.2,
    "decades ago": 2.8,
    "century": 2.5,
    "bce": 3.0,
    "bc": 3.0,
    "ce": 1.8,
    "ad": 1.8,
    "ancient": 2.8,
    "oldest": 2.5,
    "civilization": 2.4,
    "indus valley": 2.8,
    "bronze age": 2.6,
    "was founded": 2.6,
    "was established": 2.6,
    "during the": 1.4,
}

OPINION_STARTERS = {
    "i think": 3.0,
    "i believe": 3.0,
    "in my opinion": 3.2,
    "i feel": 2.8,
    "it seems": 2.6,
}

OPINION_TERMS = {
    "best": 2.0,
    "worst": 2.0,
    "failing": 2.4,
    "corrupt": 2.6,
    "terrible": 2.0,
    "awful": 2.0,
    "amazing": 1.8,
    "greatest": 2.0,
    "useless": 2.2,
    "disaster": 1.8,
    "bad": 1.4,
    "good": 1.0,
}

EXAGGERATION_TERMS = {
    "completely": 1.5,
    "totally": 1.5,
    "absolutely": 1.5,
    "always": 1.1,
    "never": 1.1,
    "massively": 1.2,
}

NORMATIVE_TERMS = {
    "should": 1.4,
    "must": 1.4,
    "ought": 1.4,
    "better": 1.2,
}

PREDICTIVE_TERMS = {
    "will become": 2.9,
    "will": 2.4,
    "expected to": 2.6,
    "likely to": 2.3,
    "projected to": 2.6,
    "forecast to": 2.6,
    "could": 1.3,
    "may": 1.2,
    "might": 1.2,
}

ENTITY_TERMS = {
    "india", "china", "russia", "usa", "united states", "uk", "germany", "france", "iran", "israel",
    "government", "parliament", "court", "president", "minister", "prime minister",
    "rbi", "fed", "nasa", "who", "un", "imf", "apple", "google", "microsoft",
    "amazon", "tesla", "meta", "reliance", "infosys", "tcs", "adani", "bollywood",
}

INSTITUTION_TERMS = {
    "government", "parliament", "court", "policy", "president", "minister",
    "prime minister", "rbi", "fed", "central bank", "repo rate", "inflation",
}

SUBJECTIVE_INSTITUTION_PATTERNS = (
    r"\b(?:corrupt|bad|weak|failing|terrible|useless)\s+(?:government|policy|leadership|court|minister|president)\b",
    r"\b(?:government|policy|leadership|court|minister|president)\s+(?:is|are|was|were)\s+(?:(?:completely|totally|absolutely)\s+)?(?:corrupt|bad|weak|failing|terrible|useless)\b",
)

CURRENT_YEAR = datetime.now().year


def classify_claims(claims: list, raw_text: str = "") -> dict:
    """Classify individual claims and derive the overall claim context."""
    annotated_claims = []
    aggregate_scores = {claim_type: 0.0 for claim_type in ALL_TYPES}
    aggregate_reasons: dict[str, list[str]] = {claim_type: [] for claim_type in ALL_TYPES}

    if not claims and raw_text.strip():
        claims = [{
            "text": raw_text.strip()[:300],
            "type": "general",
            "confidence": 0.5,
            "original": raw_text.strip()[:300],
        }]

    raw_text = (raw_text or "").strip()
    if _is_query(raw_text):
        query_result = _build_special_result(
            claim_text=raw_text,
            claim_type="query_claim",
            confidence=0.96,
            reasons=["Input is phrased as a question rather than a factual assertion"],
            scores={"query_claim": 4.0},
        )
        return {
            "primary_type": "query_claim",
            "confidence": 0.96,
            "routing": "query",
            "scores": query_result["scores"],
            "weights": {"source": 0.5, "llm": 0.0},
            "reasons": query_result["reasons"],
            "claims": [_merge_claim_context(claims[0], query_result)] if claims else [],
        }

    for claim in claims:
        claim_text = claim.get("text", "")
        claim_original = claim.get("original") or claim_text
        if len(claims) == 1 and raw_text and claim_original.lower() == claim_text.lower():
            claim_original = raw_text
        result = _classify_text(claim_text, claim_original)
        annotated_claim = _merge_claim_context(claim, result)
        annotated_claims.append(annotated_claim)

        claim_weight = 0.6 + (0.4 * max(float(claim.get("confidence", 0.5) or 0.5), 0.0))
        for claim_type, score in result["scores"].items():
            aggregate_scores[claim_type] += score * claim_weight
            if score > 0 and len(aggregate_reasons[claim_type]) < 5:
                aggregate_reasons[claim_type].extend(result["reasons"][:2])

    primary = _finalize_scores(aggregate_scores, raw_text)
    primary_type = primary["claim_type"]
    confidence = primary["confidence"]
    routing = _routing_for_type(primary_type)
    weights = _weights_for_type(primary_type, confidence)

    return {
        "primary_type": primary_type,
        "confidence": confidence,
        "routing": routing,
        "scores": {k: round(v, 4) for k, v in aggregate_scores.items()},
        "weights": weights,
        "reasons": _dedupe(primary["reasons"] or aggregate_reasons.get(primary_type, []))[:4],
        "claims": annotated_claims,
    }


def should_run_llm_review(
    claim_context: dict,
    fact_results: dict,
    semantic_results: list,
) -> bool:
    """Run Groq only when the local classifier or source evidence leaves meaningful uncertainty."""
    primary_type = claim_context.get("primary_type")
    confidence = float(claim_context.get("confidence", 0) or 0)
    if primary_type in {"query_claim", "opinion", "predictive_claim"}:
        return False
    if primary_type in {"evergreen_fact", "historical_claim", "mixed", "unknown_signal"}:
        return True
    if confidence < 0.7:
        return True
    if not fact_results.get("evidence_found"):
        return True
    if any(result.get("match_type") in {"strong_match", "partial_match"} for result in semantic_results):
        return False
    return True


def build_skipped_llm_review(input_text: str, reason: str) -> dict:
    """Return a consistent payload when the Groq review is intentionally skipped."""
    return {
        "enabled": False,
        "available": False,
        "verdict": "UNVERIFIED",
        "label": "Skipped",
        "confidence": None,
        "summary": reason,
        "reasoning": [],
        "checked_claim": (input_text or "").strip()[:500],
        "source_type": "llm_model_knowledge",
        "source_label": "Groq model knowledge (not live news sources)",
        "model": None,
    }


def _classify_text(text: str, original_text: str | None = None) -> dict:
    original_text = (original_text or text or "").strip()
    text = (text or "").strip().lower()
    if not text:
        return _build_special_result(
            claim_text=text,
            claim_type="unknown_signal",
            confidence=0.0,
            reasons=["Input text is empty after preprocessing"],
            scores={"unknown_signal": 0.0},
        )

    if _is_query(text):
        return _build_special_result(
            claim_text=text,
            claim_type="query_claim",
            confidence=0.96,
            reasons=["Claim text is framed as a question"],
            scores={"query_claim": 4.0},
        )

    scores = {claim_type: 0.0 for claim_type in ALL_TYPES}
    reasons: list[str] = []
    nlp_view = build_nlp_view(original_text)
    has_action_verb = has_noncopular_verb(nlp_view)

    breaking_hits = _apply_term_weights(nlp_view, BREAKING_TERMS, scores, "breaking_news", reasons)
    _apply_term_weights(nlp_view, EVENT_VERBS, scores, "breaking_news", reasons)
    _apply_term_weights(nlp_view, EVENT_VERBS, scores, "current_affairs", [])
    current_hits = _apply_term_weights(nlp_view, CURRENT_AFFAIRS_TERMS, scores, "current_affairs", reasons)

    evergreen_pattern_hits = _apply_pattern_weights(text, EVERGREEN_PATTERNS, scores, "evergreen_fact", reasons)
    evergreen_hits = _apply_term_weights(nlp_view, EVERGREEN_TERMS, scores, "evergreen_fact", reasons)
    historical_hits = _apply_term_weights(nlp_view, HISTORICAL_TERMS, scores, "historical_claim", reasons)

    opinion_hits = _apply_term_weights(nlp_view, OPINION_TERMS, scores, "opinion", reasons)
    _apply_term_weights(nlp_view, EXAGGERATION_TERMS, scores, "opinion", reasons)
    _apply_term_weights(nlp_view, NORMATIVE_TERMS, scores, "opinion", reasons)
    predictive_hits = _apply_term_weights(nlp_view, PREDICTIVE_TERMS, scores, "predictive_claim", reasons)
    if "will" in text and "become" in text:
        scores["predictive_claim"] += 1.0
        reasons.append("Future-tense outcome wording suggests a prediction")

    for starter, weight in OPINION_STARTERS.items():
        if text.startswith(starter):
            scores["opinion"] += weight
            reasons.append("Contains an explicit opinion lead-in")

    for pattern in SUBJECTIVE_INSTITUTION_PATTERNS:
        if re.search(pattern, text):
            scores["opinion"] += 3.0
            reasons.append("Uses subjective language tied to an institution or policy")

    entity_signal = max(_entity_signal(text), dynamic_entity_signal(nlp_view))
    if entity_signal > 0:
        scores["current_affairs"] += entity_signal
        reasons.append(
            "Contains named-entity style institutional or country references"
            if not nlp_view.entities
            else "Named entities boost public-affairs relevance"
        )

    has_weighted_event = has_entity_event_pattern(nlp_view, set(EVENT_VERBS)) or _has_weighted_term(text, EVENT_VERBS)

    if entity_signal > 0 and has_weighted_event:
        scores["current_affairs"] += 2.4
        reasons.append("Entity + event-verb combination suggests an ongoing public-affairs claim")
        scores["breaking_news"] += 1.2
        reasons.append("Entity + event-verb combination also increases breaking-news likelihood")
    elif entity_signal > 0 and has_action_verb and not is_dynamic_copular_clause(nlp_view):
        scores["current_affairs"] += 1.5
        reasons.append("Named entities paired with an action verb resemble a reportable public-affairs headline")
        if len(nlp_view.entities) >= 2:
            scores["breaking_news"] += 0.8
            reasons.append("Multiple named entities plus an action verb increase headline-style recency confidence")

    if entity_signal > 0 and (_has_weighted_term(text, BREAKING_TERMS) or count_recency_markers(nlp_view) > 0):
        scores["breaking_news"] += 1.8
        reasons.append("Entity + recency combination suggests a breaking-news style claim")

    if entity_signal > 0 and evergreen_pattern_hits and not is_dynamic_copular_clause(nlp_view):
        scores["evergreen_fact"] += 1.2
        reasons.append("Stable descriptive wording about a named entity suggests an evergreen fact")

    scores = _apply_year_logic(text, scores, reasons)
    if re.search(r"\b\d{1,4}\s*(?:bce|bc|ce|ad)\b", text):
        scores["historical_claim"] += 3.2
        scores["breaking_news"] = max(scores["breaking_news"] - 1.2, 0.0)
        scores["current_affairs"] = max(scores["current_affairs"] - 1.0, 0.0)
        reasons.append("Ancient or era-based dating strongly indicates a historical claim")

    recency_markers = count_recency_markers(nlp_view)
    if recency_markers:
        scores["breaking_news"] += min(3.0, 1.1 * recency_markers)
        reasons.append("Explicit date or recency markers strengthen the breaking-news signal")

    if scores["predictive_claim"] > 0 and _has_weighted_term(text, CURRENT_AFFAIRS_TERMS):
        scores["predictive_claim"] += 0.6
        reasons.append("Future-tense wording points to a prediction rather than a verifiable present fact")

    if scores["opinion"] > 0 and not _has_weighted_term(text, EVENT_VERBS):
        scores["opinion"] += 0.6

    if evergreen_hits and not breaking_hits and not current_hits and not historical_hits:
        scores["evergreen_fact"] += 0.7

    if re.search(r"\bone of the oldest\b", text):
        scores["historical_claim"] += 1.8
        scores["evergreen_fact"] += 1.2
        reasons.append("Superlative historical phrasing suggests an established historical fact")

    if is_dynamic_copular_clause(nlp_view):
        scores["evergreen_fact"] = max(scores["evergreen_fact"] - 2.0, 0.0)
        reasons.append("Dynamic 'is/are + adjective/action' structure reduces evergreen confidence")

    if not _has_weighted_term(text, BREAKING_TERMS) and not _has_year(text) and evergreen_pattern_hits and not is_dynamic_copular_clause(nlp_view):
        scores["evergreen_fact"] += 0.5

    return _finalize_scores(scores, text, reasons)


def _finalize_scores(scores: dict[str, float], text: str, reasons: list[str] | None = None) -> dict:
    reasons = reasons or []
    scores = {claim_type: max(score, 0.0) for claim_type, score in scores.items()}
    factual_scores = {claim_type: scores.get(claim_type, 0.0) for claim_type in FACTUAL_TYPES}
    special_scores = {
        "opinion": scores.get("opinion", 0.0),
        "predictive_claim": scores.get("predictive_claim", 0.0),
    }

    top_factual_type, top_factual_score = max(factual_scores.items(), key=lambda item: item[1])
    top_special_type, top_special_score = max(special_scores.items(), key=lambda item: item[1])
    factual_total = sum(factual_scores.values())
    total_signal = sum(scores.values())

    if top_special_score >= 3.0 and top_special_score >= top_factual_score + 0.8:
        confidence = _confidence_from_scores(top_special_score, top_factual_score, total_signal)
        return _build_special_result(
            claim_text=text,
            claim_type=top_special_type,
            confidence=confidence,
            reasons=reasons or [_label_for_type(top_special_type)],
            scores=scores,
        )

    if top_factual_score < 2.5 and factual_total < 5.0:
        confidence = _confidence_from_scores(top_factual_score, top_special_score, max(factual_total, 0.1))
        return _build_special_result(
            claim_text=text,
            claim_type="unknown_signal",
            confidence=min(confidence, 0.4),
            reasons=reasons or ["Insufficient factual signal for reliable claim typing"],
            scores=scores,
        )

    second_factual_score = sorted(factual_scores.values(), reverse=True)[1]
    confidence = _confidence_from_scores(top_factual_score, second_factual_score, factual_total)
    if confidence < 0.6:
        return _build_special_result(
            claim_text=text,
            claim_type="mixed",
            confidence=confidence,
            reasons=(reasons or []) + ["Signals are split across multiple factual claim types"],
            scores=scores,
        )

    return {
        "claim_type": top_factual_type,
        "confidence": confidence,
        "routing": _routing_for_type(top_factual_type),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "weights": _weights_for_type(top_factual_type, confidence),
        "reasons": _dedupe(reasons)[:4] or [_label_for_type(top_factual_type)],
    }


def _weights_for_type(claim_type: str, confidence: float) -> dict[str, float]:
    base_weights = {
        "breaking_news": {"source": 0.85, "llm": 0.15},
        "current_affairs": {"source": 0.75, "llm": 0.25},
        "evergreen_fact": {"source": 0.55, "llm": 0.45},
        "historical_claim": {"source": 0.65, "llm": 0.35},
        "mixed": {"source": 0.65, "llm": 0.35},
        "unknown_signal": {"source": 0.5, "llm": 0.5},
        "query_claim": {"source": 0.5, "llm": 0.0},
        "opinion": {"source": 0.5, "llm": 0.0},
        "predictive_claim": {"source": 0.5, "llm": 0.0},
    }
    weights = dict(base_weights.get(claim_type, {"source": 0.7, "llm": 0.3}))

    if claim_type in FACTUAL_TYPES | {"mixed", "unknown_signal"}:
        if confidence < 0.75:
            shift = min(0.12, (0.75 - confidence) * 0.3)
            weights["source"] = max(0.45, weights["source"] - shift)
            weights["llm"] = min(0.55, 1 - weights["source"])
        elif confidence > 0.85 and claim_type in {"breaking_news", "current_affairs", "historical_claim"}:
            shift = min(0.06, (confidence - 0.85) * 0.25)
            weights["source"] = min(0.9, weights["source"] + shift)
            weights["llm"] = max(0.1, 1 - weights["source"])

    total = weights["source"] + weights["llm"]
    return {
        "source": round(weights["source"] / max(total, 1e-6), 4),
        "llm": round(weights["llm"] / max(total, 1e-6), 4),
    }


def _routing_for_type(claim_type: str) -> str:
    if claim_type == "query_claim":
        return "query"
    if claim_type == "opinion":
        return "opinion"
    if claim_type == "predictive_claim":
        return "predictive"
    if claim_type == "unknown_signal":
        return "insufficient_signal"
    return "standard"


def _confidence_from_scores(top_score: float, second_score: float, total_score: float) -> float:
    relative_conf = top_score / max(total_score, 1e-6)
    margin_conf = (top_score - second_score) / max(top_score, 1e-6) if top_score > 0 else 0.0
    absolute_conf = min(top_score / 6.0, 1.0)
    confidence = (0.45 * relative_conf) + (0.35 * margin_conf) + (0.2 * absolute_conf)
    return round(min(max(confidence, 0.0), 1.0), 4)


def _apply_term_weights(nlp_view, weights: dict[str, float], scores: dict[str, float], target: str, reasons: list[str]) -> int:
    hit_count = 0
    for term, weight in weights.items():
        if contains_term(nlp_view, term):
            scores[target] += weight
            hit_count += 1
            if len(reasons) < 8:
                reasons.append(f"Matched `{term}`")
    return hit_count


def _apply_pattern_weights(text: str, patterns: dict[str, float], scores: dict[str, float], target: str, reasons: list[str]) -> int:
    hit_count = 0
    for pattern, weight in patterns.items():
        if re.search(pattern, text):
            scores[target] += weight
            hit_count += 1
            if len(reasons) < 8:
                reasons.append("Matched a stable descriptive sentence pattern")
    return hit_count


def _entity_signal(text: str) -> float:
    signal = 0.0
    for term in ENTITY_TERMS:
        if term in text:
            signal += 0.8 if term in INSTITUTION_TERMS else 0.55
    return min(signal, 3.0)


def _apply_year_logic(text: str, scores: dict[str, float], reasons: list[str]) -> dict[str, float]:
    years = [int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    ancient_eras = re.findall(r"\b(\d{1,4})\s*(bce|bc|ce|ad)\b", text)
    if "last year" in text:
        years.append(CURRENT_YEAR - 1)
    if "this year" in text:
        years.append(CURRENT_YEAR)

    for year in years:
        gap = CURRENT_YEAR - year
        if gap <= 1:
            scores["breaking_news"] += 1.6
            scores["current_affairs"] += 1.2
            reasons.append("References a recent year, which increases temporal sensitivity")
        elif gap <= 2:
            scores["current_affairs"] += 1.0
            scores["historical_claim"] += 1.4
            reasons.append("References a recent-but-not-immediate year")
        else:
            scores["historical_claim"] += 3.0
            scores["breaking_news"] = max(scores["breaking_news"] - 1.2, 0.0)
            scores["current_affairs"] = max(scores["current_affairs"] - 0.8, 0.0)
            reasons.append("References an older year, which shifts the claim toward historical context")

    for era_year, era_label in ancient_eras:
        scores["historical_claim"] += 3.0
        if era_label in {"bce", "bc"}:
            scores["evergreen_fact"] += 0.8
        scores["breaking_news"] = max(scores["breaking_news"] - 1.2, 0.0)
        scores["current_affairs"] = max(scores["current_affairs"] - 1.0, 0.0)
        reasons.append("Era-based dating points to a historical claim rather than current affairs")

    return scores


def _is_query(text: str) -> bool:
    text = (text or "").strip().lower()
    return text.endswith("?") or any(text.startswith(prefix) for prefix in QUESTION_PREFIXES)


def _has_year(text: str) -> bool:
    return bool(re.search(r"\b(19\d{2}|20\d{2})\b", text))


def _has_weighted_term(text: str, weights: dict[str, float]) -> bool:
    return any(term in text for term in weights)


def _merge_claim_context(claim: dict, result: dict) -> dict:
    merged = dict(claim)
    merged["claim_category"] = result.get("claim_type")
    merged["claim_category_confidence"] = result.get("confidence")
    merged["claim_category_scores"] = result.get("scores", {})
    merged["claim_routing"] = result.get("routing")
    merged["claim_reasons"] = result.get("reasons", [])
    return merged


def _build_special_result(
    claim_text: str,
    claim_type: str,
    confidence: float,
    reasons: list[str],
    scores: dict[str, float],
) -> dict:
    return {
        "claim_type": claim_type,
        "confidence": round(min(max(confidence, 0.0), 1.0), 4),
        "routing": _routing_for_type(claim_type),
        "scores": {k: round(v, 4) for k, v in {**{t: 0.0 for t in ALL_TYPES}, **scores}.items()},
        "weights": _weights_for_type(claim_type, confidence),
        "reasons": _dedupe(reasons)[:4] or [_label_for_type(claim_type)],
    }


def _label_for_type(claim_type: str) -> str:
    labels = {
        "breaking_news": "Breaking-news style recency signals dominate",
        "current_affairs": "Institutional and ongoing-public-affairs signals dominate",
        "evergreen_fact": "Stable descriptive fact patterns dominate",
        "historical_claim": "Historical time references dominate",
        "mixed": "Signals are split across multiple factual types",
        "opinion": "Subjective or evaluative language dominates",
        "predictive_claim": "Future-tense language dominates",
        "query_claim": "Input is a question rather than a claim",
        "unknown_signal": "Signal is too weak for reliable claim typing",
    }
    return labels.get(claim_type, "Claim context classified")


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
