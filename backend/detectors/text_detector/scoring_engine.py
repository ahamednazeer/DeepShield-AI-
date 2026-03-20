"""
Scoring & Decision Engine
Uses multi-provider news evidence, Wikipedia, and an auxiliary LLM review.

Component meanings:
- Provider consensus: risk derived from how many configured providers found relevant coverage
- Evidence match: risk derived from semantic alignment between claims and evidence
- Coverage risk: risk derived from how much news/Wikipedia material was retrieved
- LLM review: auxiliary risk derived from Groq model-knowledge classification
"""


def compute_final_score(
    fact_results: dict,
    semantic_results: list,
    llm_fact_check: dict | None = None,
    claim_context: dict | None = None,
) -> dict:
    """Combine source evidence with an auxiliary LLM review into the final score."""
    claim_context = claim_context or {}
    if claim_context.get("routing") in {"query", "opinion", "predictive"}:
        return _build_non_standard_result(claim_context)

    provider_component = _compute_provider_consensus_risk(fact_results)
    evidence_component = _compute_evidence_match_risk(fact_results, semantic_results)
    coverage_component = _compute_coverage_risk(fact_results)
    llm_component = _compute_llm_review_risk(llm_fact_check)
    source_weight, llm_weight = _compute_blend_weights(
        claim_context=claim_context,
        fact_results=fact_results,
        semantic_results=semantic_results,
        llm_fact_check=llm_fact_check,
    )

    source_weights = {"provider": 0.35, "evidence": 0.45, "coverage": 0.2}
    effective_weights = {
        "provider": source_weights["provider"] * source_weight,
        "evidence": source_weights["evidence"] * source_weight,
        "coverage": source_weights["coverage"] * source_weight,
        "llm": llm_weight,
    }
    source_score = (
        (source_weights["provider"] * provider_component)
        + (source_weights["evidence"] * evidence_component)
        + (source_weights["coverage"] * coverage_component)
    )
    final_score = round(
        min(
            max(
                (source_score * source_weight) + (llm_component * llm_weight),
                0.0,
            ),
            1.0,
        ),
        4,
    )

    verdict, label = _determine_verdict(
        score=final_score,
        fact_results=fact_results,
        semantic_results=semantic_results,
        provider_component=provider_component,
        evidence_component=evidence_component,
        llm_fact_check=llm_fact_check,
        claim_context=claim_context,
    )

    return {
        "score": final_score,
        "verdict": verdict,
        "label": label,
        "components": {
            "provider_consensus": {
                "score": round(provider_component, 4),
                "weight": round(effective_weights["provider"], 4),
                "weighted": round(effective_weights["provider"] * provider_component, 4),
            },
            "evidence_match": {
                "score": round(evidence_component, 4),
                "weight": round(effective_weights["evidence"], 4),
                "weighted": round(effective_weights["evidence"] * evidence_component, 4),
            },
            "coverage_risk": {
                "score": round(coverage_component, 4),
                "weight": round(effective_weights["coverage"], 4),
                "weighted": round(effective_weights["coverage"] * coverage_component, 4),
            },
            "llm_review": {
                "score": round(llm_component, 4),
                "weight": round(effective_weights["llm"], 4),
                "weighted": round(effective_weights["llm"] * llm_component, 4),
            },
        },
    }


def _compute_provider_consensus_risk(fact_results: dict) -> float:
    """Higher scores mean fewer configured providers returned coverage for the claims."""
    provider_stats = fact_results.get("provider_stats", {})
    configured_count = provider_stats.get("configured_count", 0)
    hit_count = provider_stats.get("hit_count", 0)

    if configured_count == 0:
        return 0.5

    hit_ratio = hit_count / configured_count
    if hit_ratio >= 0.75:
        return 0.2
    if hit_ratio >= 0.5:
        return 0.35
    if hit_ratio > 0:
        return 0.55
    return 0.8


def _compute_evidence_match_risk(fact_results: dict, semantic_results: list) -> float:
    """Higher scores mean the retrieved evidence does not support the claim well."""
    evidence_found = fact_results.get("evidence_found", False)
    evidence_strength = fact_results.get("evidence_strength", "none")
    provider_available = fact_results.get("news_api_available", False)
    semantic_summary = _summarize_semantic_results(semantic_results)

    if not provider_available and evidence_strength == "unavailable":
        if semantic_summary["strong_match_count"] > 0:
            return 0.3
        if semantic_summary["partial_match_count"] > 0:
            return 0.5
        if semantic_summary["weak_match_count"] > 0:
            return 0.65
        return 0.5

    if not evidence_found:
        return 0.85

    if semantic_summary["strong_match_count"] > 0:
        strength_scores = {
            "strong": 0.1,
            "moderate": 0.22,
            "weak": 0.35,
            "none": 0.5,
        }
        base_score = strength_scores.get(evidence_strength, 0.2)
        base_score += 0.1 * (1 - semantic_summary["support_ratio"])
        return min(max(base_score, 0.0), 1.0)

    if semantic_summary["partial_match_count"] > 0:
        strength_scores = {
            "strong": 0.35,
            "moderate": 0.45,
            "weak": 0.58,
            "none": 0.68,
        }
        base_score = strength_scores.get(evidence_strength, 0.5)
        base_score += 0.1 * (1 - semantic_summary["support_ratio"])
        return min(max(base_score, 0.0), 1.0)

    if semantic_summary["weak_match_count"] > 0:
        return 0.7

    return 0.78


def _compute_coverage_risk(fact_results: dict) -> float:
    """Higher scores mean fewer news or Wikipedia materials were found."""
    news_results = fact_results.get("news_results", [])
    wiki_results = fact_results.get("wiki_results", [])
    news_count = sum(result.get("total_results", 0) for result in news_results)
    wiki_count = sum(len(result.get("results", [])) for result in wiki_results)
    total_hits = news_count + wiki_count

    if not fact_results.get("news_api_available") and total_hits == 0:
        return 0.5
    if total_hits >= 20:
        return 0.2
    if total_hits >= 8:
        return 0.35
    if total_hits >= 3:
        return 0.5
    if total_hits >= 1:
        return 0.65
    return 0.8


def _compute_llm_review_risk(llm_fact_check: dict | None) -> float:
    """Convert the LLM verdict into the same fake-risk scale as the source verdict."""
    llm_fact_check = llm_fact_check or {}
    if not llm_fact_check.get("enabled") or not llm_fact_check.get("available"):
        return 0.5

    try:
        confidence = float(llm_fact_check.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = min(max(confidence, 0.0), 1.0)

    verdict = llm_fact_check.get("verdict")
    if verdict == "FAKE":
        return round(0.5 + (0.5 * confidence), 4)
    if verdict == "REAL":
        return round(0.5 - (0.5 * confidence), 4)
    return 0.5


def _compute_blend_weights(
    claim_context: dict,
    fact_results: dict,
    semantic_results: list,
    llm_fact_check: dict | None,
) -> tuple[float, float]:
    """Weight source evidence above the LLM, but let the LLM soften source-only silence."""
    llm_fact_check = llm_fact_check or {}
    if not llm_fact_check.get("enabled") or not llm_fact_check.get("available"):
        return 1.0, 0.0

    recommended = claim_context.get("weights") or {"source": 0.75, "llm": 0.25}
    source_weight = float(recommended.get("source", 0.75))
    llm_weight = float(recommended.get("llm", 0.25))

    semantic_summary = _summarize_semantic_results(semantic_results)
    if semantic_summary["strong_match_count"] > 0:
        source_weight = max(source_weight, 0.72)
        llm_weight = 1 - source_weight
    elif semantic_summary["partial_match_count"] > 0:
        source_weight = max(source_weight, 0.67)
        llm_weight = 1 - source_weight
    elif fact_results.get("evidence_found"):
        source_weight = max(source_weight, 0.6)
        llm_weight = 1 - source_weight

    total = source_weight + llm_weight
    return round(source_weight / max(total, 1e-6), 4), round(llm_weight / max(total, 1e-6), 4)


def _determine_verdict(
    score: float,
    fact_results: dict,
    semantic_results: list,
    provider_component: float,
    evidence_component: float,
    llm_fact_check: dict | None = None,
    claim_context: dict | None = None,
) -> tuple[str, str]:
    """Determine the verdict from source evidence, then soften it on strong LLM conflicts."""
    claim_context = claim_context or {}
    source_verdict, source_label = _determine_source_verdict(
        score=score,
        fact_results=fact_results,
        semantic_results=semantic_results,
        provider_component=provider_component,
        evidence_component=evidence_component,
    )
    llm_fact_check = llm_fact_check or {}
    llm_conflict = _classify_llm_conflict(source_verdict, llm_fact_check)

    if llm_conflict == "strong":
        semantic_summary = _summarize_semantic_results(semantic_results)
        has_supporting_evidence = (
            semantic_summary["strong_match_count"] > 0
            or semantic_summary["partial_match_count"] > 0
        )
        if has_supporting_evidence:
            return "UNCERTAIN", "Uncertain — Source Evidence and LLM Disagree"
        return "UNCERTAIN", "Uncertain — No Source Support and LLM Disagrees"

    if llm_conflict == "soft" and source_verdict in {"FAKE", "LIKELY_FAKE"}:
        return "UNVERIFIED", "Unverified — Mixed Source and LLM Signals"

    if (
        claim_context.get("primary_type") in {"historical_claim", "evergreen_fact"}
        and source_verdict in {"FAKE", "LIKELY_FAKE"}
        and not any(
            result.get("match_type") in {"strong_match", "partial_match"}
            for result in semantic_results
        )
        and not (llm_fact_check or {}).get("available")
    ):
        return "UNVERIFIED", "Unverified — Historical Claim Needs Supporting Evidence"

    if (
        source_verdict == "UNVERIFIED"
        and claim_context.get("primary_type") in {"evergreen_fact", "historical_claim"}
        and llm_fact_check.get("verdict") == "REAL"
        and (llm_fact_check.get("confidence") or 0) >= 0.85
        and score <= 0.35
    ):
        return "LIKELY_REAL", "Likely Real — Strong Evergreen Signals"

    if _source_direction(source_verdict) == _llm_direction(llm_fact_check):
        llm_confidence = llm_fact_check.get("confidence") or 0
        if source_verdict == "LIKELY_FAKE" and llm_fact_check.get("verdict") == "FAKE" and llm_confidence >= 0.8 and score >= 0.78:
            return "FAKE", "Fake News"
        if (
            source_verdict == "LIKELY_REAL"
            and llm_fact_check.get("verdict") == "REAL"
            and llm_confidence >= 0.8
            and score <= 0.3
            and claim_context.get("primary_type") in {"evergreen_fact", "historical_claim", "mixed"}
        ):
            return "REAL", "Verified by Sources and LLM"

    return source_verdict, source_label


def _determine_source_verdict(
    score: float,
    fact_results: dict,
    semantic_results: list,
    provider_component: float,
    evidence_component: float,
) -> tuple[str, str]:
    """Determine the verdict using only source evidence."""
    evidence_found = fact_results.get("evidence_found", False)
    provider_available = fact_results.get("news_api_available", False)
    semantic_summary = _summarize_semantic_results(semantic_results)
    has_supporting_evidence = (
        semantic_summary["strong_match_count"] > 0
        or semantic_summary["partial_match_count"] > 0
    )

    if not evidence_found and not provider_available:
        return "UNVERIFIED", "Unverified (Limited Verification Available)"

    if evidence_found and not has_supporting_evidence:
        if score >= 0.62 or provider_component >= 0.55:
            return "LIKELY_FAKE", "Likely Fake — No Supporting Evidence"
        return "UNVERIFIED", "Unverified — No Supporting Evidence"

    has_partial_match = any(
        result.get("match_type") == "partial_match"
        for result in semantic_results
    )
    if has_partial_match and 0.38 <= score <= 0.72:
        return "MISLEADING", "Misleading — Evidence Only Partially Matches"

    if semantic_summary["strong_match_count"] > 0 and evidence_component <= 0.22:
        if score <= 0.18:
            return "REAL", "Verified by News APIs and Wikipedia"
        return "LIKELY_REAL", "Likely Real — Supported by Evidence"

    if score >= 0.82:
        return "FAKE", "Fake News"
    if score >= 0.62:
        return "LIKELY_FAKE", "Likely Fake"
    if score >= 0.45:
        return "UNCERTAIN", "Uncertain — Needs More Verification"
    if score >= 0.25:
        return "LIKELY_REAL", "Likely Real — Supported by Evidence"
    return "REAL", "Verified by News APIs and Wikipedia"


def _classify_llm_conflict(source_verdict: str, llm_fact_check: dict) -> str | None:
    """Classify whether the LLM meaningfully disagrees with the source verdict."""
    if not llm_fact_check.get("enabled") or not llm_fact_check.get("available"):
        return None

    source_direction = _source_direction(source_verdict)
    llm_direction = _llm_direction(llm_fact_check)
    if source_direction == "neutral" or llm_direction == "neutral" or source_direction == llm_direction:
        return None

    try:
        confidence = float(llm_fact_check.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0

    if confidence >= 0.8:
        return "strong"
    if confidence >= 0.65:
        return "soft"
    return None


def _source_direction(verdict: str) -> str:
    if verdict in {"FAKE", "LIKELY_FAKE"}:
        return "fake"
    if verdict in {"REAL", "LIKELY_REAL"}:
        return "real"
    return "neutral"


def _llm_direction(llm_fact_check: dict) -> str:
    verdict = llm_fact_check.get("verdict")
    if verdict == "FAKE":
        return "fake"
    if verdict == "REAL":
        return "real"
    return "neutral"


def _build_non_standard_result(claim_context: dict) -> dict:
    primary_type = claim_context.get("primary_type")
    labels = {
        "query_claim": "Question — Rephrase as a Factual Claim",
        "opinion": "Opinion — Not Directly Verifiable",
        "predictive_claim": "Prediction — Cannot Be Verified Yet",
        "unknown_signal": "Too Vague to Verify",
    }
    scores = {
        "query_claim": 0.5,
        "opinion": 0.42,
        "predictive_claim": 0.48,
        "unknown_signal": 0.5,
    }
    score = scores.get(primary_type, 0.5)
    return {
        "score": score,
        "verdict": "UNVERIFIED",
        "label": labels.get(primary_type, "Unverified"),
        "components": {
            "provider_consensus": {"score": 0.0, "weight": 0.0, "weighted": 0.0},
            "evidence_match": {"score": 0.0, "weight": 0.0, "weighted": 0.0},
            "coverage_risk": {"score": 0.0, "weight": 0.0, "weighted": 0.0},
            "llm_review": {"score": 0.0, "weight": 0.0, "weighted": 0.0},
        },
    }


def _summarize_semantic_results(semantic_results: list) -> dict:
    """Aggregate semantic match quality across all extracted claims."""
    total_claims = len(semantic_results)
    strong_match_count = sum(
        1 for result in semantic_results if result.get("match_type") == "strong_match"
    )
    partial_match_count = sum(
        1 for result in semantic_results if result.get("match_type") == "partial_match"
    )
    weak_match_count = sum(
        1 for result in semantic_results if result.get("match_type") == "weak_match"
    )
    support_count = strong_match_count + partial_match_count

    return {
        "total_claims": total_claims,
        "strong_match_count": strong_match_count,
        "partial_match_count": partial_match_count,
        "weak_match_count": weak_match_count,
        "support_ratio": support_count / max(total_claims, 1),
    }
