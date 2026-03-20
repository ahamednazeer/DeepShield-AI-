"""
Explainability helpers for the multi-provider news + Wikipedia text-analysis pipeline.
"""


def generate_explanation(
    fact_results: dict,
    semantic_results: list,
    final: dict,
    llm_fact_check: dict | None = None,
    claim_context: dict | None = None,
) -> dict:
    """Build the explanation payload consumed by the text-analysis UI."""
    verdict = final.get("verdict", "UNKNOWN")
    label = final.get("label", "Unknown")
    score = final.get("score", 0)
    llm_fact_check = llm_fact_check or {}
    claim_context = claim_context or {}

    return {
        "summary": _build_summary(verdict, label, score, claim_context),
        "verdict": verdict,
        "label": label,
        "confidence_percent": round(score * 100, 1),
        "reasons": _build_reasons(fact_results, semantic_results, verdict, llm_fact_check, claim_context),
        "evidence_summary": build_evidence_summary(semantic_results),
        "signals": _build_signals(fact_results, semantic_results, verdict, llm_fact_check, claim_context),
        "recommendations": _build_recommendations(verdict, fact_results, llm_fact_check, claim_context),
        "claim_context": claim_context,
        "llm_fact_check": llm_fact_check,
        "score_breakdown": final.get("components", {}),
    }


def build_evidence_summary(semantic_results: list) -> list:
    """Summarize only semantically relevant evidence for the UI."""
    summary = []
    seen = set()

    for result in semantic_results:
        for match in result.get("matches", []):
            if match.get("match_type") not in {"strong_match", "partial_match"}:
                continue

            key = (
                match.get("type", ""),
                match.get("source", ""),
                match.get("title", ""),
                match.get("url", ""),
            )
            if key in seen:
                continue

            seen.add(key)
            summary.append({
                "type": match.get("type", "news"),
                "source": match.get("source", "Unknown"),
                "title": match.get("title", ""),
                "url": match.get("url", ""),
                "extract": (match.get("extract") or "")[:200],
            })

    if summary:
        return summary[:5]

    if any(result.get("match_type") == "weak_match" for result in semantic_results):
        return [{
            "type": "none",
            "source": "Verification",
            "title": "No closely matching evidence found",
            "extract": "Retrieved articles were only weakly related to the claim.",
            "url": "",
        }]

    return [{
        "type": "none",
        "source": "Verification",
        "title": "No closely matching evidence found",
        "extract": "The configured news providers and Wikipedia did not provide direct support for this claim.",
        "url": "",
    }]


def _build_summary(verdict: str, label: str, score: float, claim_context: dict) -> str:
    primary_type = claim_context.get("primary_type")
    if primary_type == "query_claim":
        return "This input is framed as a question. Rephrase it as a factual claim to verify it."
    if primary_type == "opinion":
        return "This input appears opinionated rather than directly verifiable."
    if primary_type == "predictive_claim":
        return "This input is a prediction and cannot be confirmed as a present fact."

    fake_confidence = round(score * 100, 1)
    if verdict in {"FAKE", "LIKELY_FAKE"}:
        summary = f"This content is assessed as {label} with {fake_confidence}% fake confidence."
        if primary_type == "unknown_signal":
            summary += " Claim typing confidence was low, but verification was still attempted."
        return summary
    if verdict in {"REAL", "LIKELY_REAL"}:
        summary = f"This content appears to be {label} with {round((1 - score) * 100, 1)}% real confidence."
        if primary_type == "unknown_signal":
            summary += " Claim typing confidence was low, but verification was still attempted."
        return summary
    if verdict == "MISLEADING":
        summary = f"This content contains misleading claims. Confidence: {fake_confidence}%."
        if primary_type == "unknown_signal":
            summary += " Claim typing confidence was low, but verification was still attempted."
        return summary
    summary = f"Verification result: {label}. Confidence: {fake_confidence}%."
    if primary_type == "unknown_signal":
        summary += " Claim typing confidence was low, but verification was still attempted."
    return summary


def _build_reasons(
    fact_results: dict,
    semantic_results: list,
    verdict: str,
    llm_fact_check: dict,
    claim_context: dict,
) -> list:
    """Build the list of key reasons for the verdict."""
    if claim_context.get("primary_type") in {"query_claim", "opinion", "predictive_claim"}:
        base = [
            f"Claim type classified as {claim_context['primary_type'].replace('_', ' ')} at {round((claim_context.get('confidence') or 0) * 100)}% confidence"
        ]
        base.extend(claim_context.get("reasons", []))
        return base[:5]

    reasons = []
    if claim_context.get("primary_type"):
        reasons.append(
            f"Claim type classified as {claim_context['primary_type'].replace('_', ' ')} at {round((claim_context.get('confidence') or 0) * 100)}% confidence"
        )
    provider_stats = fact_results.get("provider_stats", {})

    if provider_stats.get("configured_count", 0) > 0:
        reasons.append(
            f"{provider_stats.get('hit_count', 0)} of {provider_stats.get('configured_count', 0)} configured news provider(s) returned coverage"
        )

    if not fact_results.get("evidence_found"):
        reasons.append("No supporting evidence was found in the configured news providers or Wikipedia")
    elif any(result.get("match_type") == "strong_match" for result in semantic_results):
        reasons.append("Retrieved evidence closely matches the extracted claim")
    elif any(result.get("match_type") == "partial_match" for result in semantic_results):
        reasons.append("Available evidence only partially matches the extracted claim")
    elif any(result.get("match_type") == "weak_match" for result in semantic_results):
        reasons.append("Retrieved articles were only weakly related to the extracted claim")
    else:
        reasons.append("Retrieved evidence did not directly support the extracted claim")

    if fact_results.get("wiki_found"):
        reasons.append("Wikipedia returned additional background information for the query")

    if verdict in {"LIKELY_FAKE", "FAKE"} and not any(
        result.get("match_type") in {"strong_match", "partial_match"}
        for result in semantic_results
    ):
        reasons.append("No provider returned evidence that directly substantiated the claim")

    if llm_fact_check.get("enabled"):
        llm_summary = f"Groq model-only check returned {llm_fact_check.get('verdict', 'UNVERIFIED')}"
        if llm_fact_check.get("confidence") is not None:
            llm_summary += f" at {round(llm_fact_check['confidence'] * 100)}% confidence"
        reasons.append(llm_summary)
        if _is_llm_conflict(verdict, llm_fact_check):
            reasons.append("Final verdict was softened because source evidence and the LLM disagreed")

    return reasons[:5]


def _build_signals(
    fact_results: dict,
    semantic_results: list,
    verdict: str,
    llm_fact_check: dict,
    claim_context: dict,
) -> list:
    """Provide lightweight analysis signals for the UI."""
    provider_stats = fact_results.get("provider_stats", {})
    providers = provider_stats.get("configured_providers", [])
    if claim_context.get("primary_type") in {"query_claim", "opinion", "predictive_claim"}:
        return [
            {
                "type": "analysis_method",
                "severity": "info",
                "detail": "Analysis performed using: local claim typing",
            },
            {
                "type": "claim_context",
                "severity": "info",
                "detail": (
                    f"Claim context: {claim_context['primary_type'].replace('_', ' ')}"
                    f" ({round((claim_context.get('confidence') or 0) * 100)}% confidence)"
                ),
            },
        ]
    method_detail = "Analysis performed using: " + (
        " + ".join(providers + ["Wikipedia"]) if providers else "Wikipedia only"
    )

    signals = [{
        "type": "analysis_method",
        "severity": "info",
        "detail": method_detail,
    }]
    if claim_context.get("primary_type"):
        signals.append({
            "type": "claim_context",
            "severity": "info",
            "detail": (
                f"Claim context: {claim_context['primary_type'].replace('_', ' ')}"
                f" ({round((claim_context.get('confidence') or 0) * 100)}% confidence)"
            ),
        })

    news_count = sum(result.get("total_results", 0) for result in fact_results.get("news_results", []))
    wiki_count = sum(len(result.get("results", [])) for result in fact_results.get("wiki_results", []))
    signals.append({
        "type": "source_counts",
        "severity": "info",
        "detail": f"Retrieved {news_count} news hit(s) and {wiki_count} Wikipedia result(s)",
    })

    if any(result.get("match_type") == "partial_match" for result in semantic_results):
        signals.append({
            "type": "partial_match",
            "severity": "medium",
            "detail": "Evidence only partially matched the extracted claims",
        })
    elif any(result.get("match_type") == "no_match" for result in semantic_results):
        signals.append({
            "type": "no_support",
            "severity": "medium",
            "detail": "Retrieved evidence did not directly support the extracted claims",
        })

    if llm_fact_check.get("enabled"):
        signals.append({
            "type": "llm_source",
            "severity": "info" if llm_fact_check.get("available") else "medium",
            "detail": "Groq LLM check uses model knowledge only, not live news sources",
        })
        signals.append({
            "type": "llm_verdict",
            "severity": "info" if llm_fact_check.get("available") else "medium",
            "detail": (
                f"Groq LLM verdict: {llm_fact_check.get('verdict', 'UNVERIFIED')}"
                + (
                    f" ({round(llm_fact_check['confidence'] * 100)}% confidence)"
                    if llm_fact_check.get("confidence") is not None
                    else ""
                )
            ),
        })
        signals.append({
            "type": "verdict_blend",
            "severity": "info",
            "detail": "Final verdict blends source evidence with a lower-weight LLM review",
        })
        if _is_llm_conflict(verdict, llm_fact_check):
            signals.append({
                "type": "llm_conflict",
                "severity": "medium",
                "detail": "Source evidence and the LLM disagreed, so the final verdict was downgraded",
            })

    return signals


def _build_recommendations(verdict: str, fact_results: dict, llm_fact_check: dict, claim_context: dict) -> list:
    """Provide simple recommendations from the final verdict."""
    if claim_context.get("primary_type") == "query_claim":
        return ["Rewrite the question as a direct factual statement before fact-checking it"]
    if claim_context.get("primary_type") == "opinion":
        return ["Separate subjective opinion from factual assertions before verification"]
    if claim_context.get("primary_type") == "predictive_claim":
        return ["Treat this as a forecast and verify it against future outcomes or cited projections"]
    if verdict in {"FAKE", "LIKELY_FAKE"}:
        recs = ["Do not share this content without verification"]
    elif verdict == "MISLEADING":
        recs = ["Cross-check the claim with multiple reliable outlets"]
    elif verdict == "UNVERIFIED":
        recs = ["Wait for direct reporting or official confirmation before sharing"]
    else:
        recs = ["Cross-reference the claim with the cited sources"]

    if fact_results.get("provider_stats", {}).get("configured_count", 0) == 0:
        recs.append("Add one or more provider API keys to improve verification coverage")
    if claim_context.get("primary_type") == "unknown_signal":
        recs.append("Add concrete details such as who, what, when, and where to improve claim typing")
    if llm_fact_check.get("enabled") and llm_fact_check.get("verdict") == "UNVERIFIED":
        recs.append("Treat the LLM check as inconclusive unless live evidence also supports the claim")
    if _is_llm_conflict(verdict, llm_fact_check):
        recs.append("Review the cited evidence manually when source checks and the LLM disagree")
    return recs[:5]


def _is_llm_conflict(final_verdict: str | None, llm_fact_check: dict) -> bool:
    if not llm_fact_check.get("enabled") or not llm_fact_check.get("available"):
        return False

    llm_verdict = llm_fact_check.get("verdict")
    if final_verdict in {"FAKE", "LIKELY_FAKE"} and llm_verdict == "REAL":
        return True
    if final_verdict in {"REAL", "LIKELY_REAL"} and llm_verdict == "FAKE":
        return True
    return False
