"""
Text-based analysis pipeline using multiple news providers, Wikipedia,
Groq model review, and local semantic matching over the retrieved evidence.
"""

import time

from .preprocessor import preprocess_text
from .claim_extractor import extract_claims
from .claim_context import (
    build_skipped_llm_review,
    classify_claims,
    should_run_llm_review,
)
from .query_generator import generate_queries
from .fact_checker import check_facts
from .groq_fact_checker import run_llm_fact_check
from .semantic_matcher import match_claims_to_evidence
from .scoring_engine import compute_final_score
from .explainer import generate_explanation


async def analyze_text(text: str, source_url: str = None) -> dict:
    """
    Full text-analysis pipeline.

    Flow:
    1. Preprocess text
    2. Extract claims and search queries
    3. Classify the claim context and decide whether it is factual enough to verify
    4. Retrieve evidence from the configured news providers and Wikipedia
    5. Optionally run a fallback Groq model-knowledge fact check
    6. Match claims against the retrieved evidence
    7. Fuse provider consensus, match quality, coverage, and claim context into the final score
    8. Generate the explanation payload
    """
    start_time = time.time()
    preprocessed = preprocess_text(text)

    claims = extract_claims(
        preprocessed["clean_text"],
        preprocessed["sentences"],
        preprocessed.get("original_sentences"),
    )
    claim_context = classify_claims(claims, raw_text=preprocessed["clean_text"])
    claims = claim_context.get("claims", claims)
    queries = generate_queries(claims)

    if claim_context.get("routing") in {"query", "opinion", "predictive"}:
        fact_results = _empty_fact_results()
        semantic_results = []
        llm_fact_check = build_skipped_llm_review(
            preprocessed["clean_text"],
            _llm_skip_reason(claim_context),
        )
    else:
        fact_results = await check_facts(queries, claims)
        semantic_results = match_claims_to_evidence(claims, fact_results)
        if should_run_llm_review(claim_context, fact_results, semantic_results):
            llm_fact_check = await run_llm_fact_check(preprocessed["clean_text"], claims)
        else:
            llm_fact_check = build_skipped_llm_review(
                preprocessed["clean_text"],
                "Groq review skipped because rule-based claim typing and source evidence were strong enough.",
            )

    final = compute_final_score(
        fact_results=fact_results,
        semantic_results=semantic_results,
        llm_fact_check=llm_fact_check,
        claim_context=claim_context,
    )

    provider_consensus = final["components"]["provider_consensus"]["score"]
    coverage_risk = final["components"]["coverage_risk"]["score"]
    explanation = generate_explanation(
        fact_results=fact_results,
        semantic_results=semantic_results,
        final=final,
        llm_fact_check=llm_fact_check,
        claim_context=claim_context,
    )

    classification = {
        "fake_probability": provider_consensus,
        "classification": "FAKE" if provider_consensus >= 0.5 else "REAL",
        "confidence": round(abs(provider_consensus - 0.5) * 2, 4),
        "method": "multi_news_plus_groq",
        "signals": [],
        "llm_verdict": llm_fact_check.get("verdict"),
        "llm_confidence": llm_fact_check.get("confidence"),
        "claim_type": claim_context.get("primary_type"),
        "claim_type_confidence": claim_context.get("confidence"),
    }

    processing_time = round(time.time() - start_time, 2)

    return {
        "input_text": text,
        "source_url": source_url,
        "preprocessed": preprocessed,
        "classification": classification,
        "claims": claims,
        "queries": queries,
        "fact_results": fact_results,
        "credibility": {
            "score": coverage_risk,
            "rating": "COVERAGE_RISK",
            "domain": None,
            "details": ["Coverage risk is derived from the configured news providers and Wikipedia"],
            "is_satire": False,
        },
        "semantic_results": semantic_results,
        "fact_score": final["components"]["evidence_match"]["score"],
        "final_score": final["score"],
        "verdict": final["verdict"],
        "verdict_label": final["label"],
        "claim_context": claim_context,
        "llm_fact_check": llm_fact_check,
        "explanation": explanation,
        "processing_time": processing_time,
    }


def _empty_fact_results() -> dict:
    return {
        "news_results": [],
        "wiki_results": [],
        "provider_results": {},
        "provider_stats": {
            "configured_providers": [],
            "configured_count": 0,
            "available_providers": [],
            "available_count": 0,
            "hit_providers": [],
            "hit_count": 0,
        },
        "news_api_available": False,
        "evidence_found": False,
        "evidence_strength": "none",
        "news_found": False,
        "wiki_found": False,
        "wiki_available": False,
    }


def _llm_skip_reason(claim_context: dict) -> str:
    labels = {
        "query_claim": "Groq review skipped because the input is phrased as a question rather than a claim.",
        "opinion": "Groq review skipped because the input appears to be opinionated rather than directly verifiable.",
        "predictive_claim": "Groq review skipped because the input is predictive and cannot be fact-checked as a present fact.",
        "unknown_signal": "Groq review skipped because the input is too weak or vague for reliable fact-checking.",
    }
    return labels.get(
        claim_context.get("primary_type"),
        "Groq review skipped for this claim context.",
    )
