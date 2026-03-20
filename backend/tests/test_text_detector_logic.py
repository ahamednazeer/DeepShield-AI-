import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.detectors.text_detector import analyze_text
from backend.detectors.text_detector.claim_context import classify_claims
from backend.detectors.text_detector.explainer import generate_explanation
from backend.detectors.text_detector.groq_fact_checker import (
    _extract_json_object,
    _normalize_llm_payload,
)
from backend.detectors.text_detector.scoring_engine import compute_final_score
from backend.detectors.text_detector.semantic_matcher import match_claims_to_evidence


class TextDetectorLogicTests(unittest.TestCase):
    def test_semantic_matcher_rejects_single_shared_topic_term(self):
        claims = [{"text": "India is dictatorship country"}]
        fact_results = {
            "news_results": [
                {
                    "claim_index": 0,
                    "articles": [
                        {
                            "title": "How India's Dominance Reshaped Cricket",
                            "description": "A look at cricket strategy",
                            "source": "Foreign Policy",
                            "url": "https://example.com/cricket",
                        }
                    ],
                }
            ],
            "wiki_results": [],
        }

        result = match_claims_to_evidence(claims, fact_results)[0]

        self.assertEqual(result["match_type"], "no_match")
        self.assertEqual(result["overlap_terms"], ["india"])

    def test_scoring_marks_unsupported_search_hits_as_unverified(self):
        fact_results = {
            "evidence_found": True,
            "evidence_strength": "moderate",
            "news_api_available": True,
            "provider_stats": {
                "configured_count": 4,
                "hit_count": 1,
                "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
            },
            "news_results": [{"total_results": 10}],
            "wiki_results": [],
        }
        semantic_results = [
            {
                "match_type": "no_match",
                "best_similarity": 0.18,
                "best_relevance": 0.22,
                "matches": [],
            }
        ]

        final = compute_final_score(
            fact_results=fact_results,
            semantic_results=semantic_results,
        )

        self.assertEqual(final["verdict"], "LIKELY_FAKE")
        self.assertAlmostEqual(
            final["components"]["evidence_match"]["score"], 0.78, places=2
        )
        self.assertAlmostEqual(
            final["components"]["provider_consensus"]["score"], 0.55, places=2
        )

    def test_scoring_treats_provider_outage_as_limited_verification(self):
        final = compute_final_score(
            fact_results={
                "evidence_found": False,
                "evidence_strength": "unavailable",
                "news_api_available": False,
                "provider_stats": {
                    "configured_count": 4,
                    "available_count": 0,
                    "hit_count": 0,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [],
                "wiki_results": [{"results": [], "available": False}],
            },
            semantic_results=[],
            claim_context={
                "primary_type": "current_affairs",
                "routing": "standard",
                "weights": {"source": 0.75, "llm": 0.25},
            },
            llm_fact_check={"enabled": False, "available": False, "verdict": "UNVERIFIED"},
        )

        self.assertEqual(final["verdict"], "UNVERIFIED")
        self.assertIn("Limited Verification", final["label"])

    def test_unknown_signal_still_attempts_fact_and_llm_verification(self):
        claim_context = {
            "primary_type": "unknown_signal",
            "confidence": 0.4,
            "routing": "insufficient_signal",
            "weights": {"source": 0.5, "llm": 0.5},
            "claims": [{
                "text": "india sends warships",
                "confidence": 0.5,
                "original": "India Sends Warships",
                "claim_category": "unknown_signal",
            }],
        }
        fact_results = {
            "news_results": [],
            "wiki_results": [],
            "provider_results": {},
            "provider_stats": {
                "configured_providers": ["NewsData.io"],
                "configured_count": 1,
                "available_providers": ["NewsData.io"],
                "available_count": 1,
                "hit_providers": [],
                "hit_count": 0,
            },
            "news_api_available": True,
            "evidence_found": False,
            "evidence_strength": "none",
            "news_found": False,
            "wiki_found": False,
            "wiki_available": True,
        }
        llm_fact_check = {
            "enabled": True,
            "available": True,
            "verdict": "UNVERIFIED",
            "label": "UNVERIFIED",
            "confidence": 0.55,
            "summary": "Model knowledge alone is inconclusive.",
            "reasoning": [],
            "source_type": "llm_model_knowledge",
            "source_label": "Groq model knowledge (not live news sources)",
            "model": "llama-3.3-70b-versatile",
        }

        with (
            patch("backend.detectors.text_detector.preprocess_text", return_value={
                "clean_text": "India Sends Warships",
                "sentences": ["india sends warships"],
                "original_sentences": ["India Sends Warships"],
            }),
            patch("backend.detectors.text_detector.extract_claims", return_value=[{
                "text": "india sends warships",
                "confidence": 0.5,
                "original": "India Sends Warships",
            }]),
            patch("backend.detectors.text_detector.classify_claims", return_value=claim_context),
            patch("backend.detectors.text_detector.generate_queries", return_value=[{
                "claim_index": 0,
                "query": "India Sends Warships",
            }]),
            patch("backend.detectors.text_detector.check_facts", new=AsyncMock(return_value=fact_results)) as mock_check_facts,
            patch("backend.detectors.text_detector.match_claims_to_evidence", return_value=[]),
            patch("backend.detectors.text_detector.should_run_llm_review", return_value=True),
            patch("backend.detectors.text_detector.run_llm_fact_check", new=AsyncMock(return_value=llm_fact_check)) as mock_run_llm,
        ):
            result = asyncio.run(analyze_text("India Sends Warships"))

        mock_check_facts.assert_awaited_once()
        mock_run_llm.assert_awaited_once()
        self.assertEqual(result["claim_context"]["primary_type"], "unknown_signal")
        self.assertNotIn("Too Vague", result["verdict_label"])
        self.assertTrue(result["llm_fact_check"]["enabled"])

    def test_explainer_hides_irrelevant_evidence_cards(self):
        explanation = generate_explanation(
            fact_results={
                "evidence_found": True,
                "evidence_strength": "moderate",
                "news_found": True,
                "wiki_found": False,
                "news_api_available": True,
                "provider_stats": {
                    "configured_count": 4,
                    "hit_count": 1,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [{"total_results": 10}],
                "wiki_results": [],
            },
            semantic_results=[
                {
                    "match_type": "no_match",
                    "matches": [
                        {
                            "type": "news",
                            "source": "Foreign Policy",
                            "title": "How India's Dominance Reshaped Cricket",
                            "url": "https://example.com/cricket",
                            "extract": "A look at cricket strategy",
                            "match_type": "no_match",
                        }
                    ],
                }
            ],
            final={
                "verdict": "UNVERIFIED",
                "score": 0.54,
                "label": "Unverified — No Supporting Evidence",
                "components": {},
            },
        )

        self.assertEqual(explanation["evidence_summary"][0]["type"], "none")
        self.assertIn("Unverified", explanation["summary"])

    def test_financial_headline_paraphrase_counts_as_supporting_match(self):
        claims = [{"text": "european stocks close lower as attention turns to the fed"}]
        fact_results = {
            "news_results": [
                {
                    "claim_index": 0,
                    "total_results": 17,
                    "articles": [
                        {
                            "provider": "WorldNewsAPI",
                            "title": "European shares end lower as focus shifts to Fed",
                            "description": "Markets in Europe closed lower as investors awaited signals from the U.S. Federal Reserve.",
                            "source": "Reuters",
                            "url": "https://example.com/markets",
                        }
                    ],
                }
            ],
            "wiki_results": [],
            "evidence_found": True,
            "evidence_strength": "moderate",
            "news_api_available": True,
            "provider_stats": {
                "configured_count": 4,
                "hit_count": 2,
                "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
            },
        }

        semantic_results = match_claims_to_evidence(claims, fact_results)
        final = compute_final_score(
            fact_results=fact_results,
            semantic_results=semantic_results,
        )

        self.assertEqual(semantic_results[0]["match_type"], "strong_match")
        self.assertEqual(final["verdict"], "LIKELY_REAL")

    def test_groq_fact_checker_normalizes_json_response(self):
        payload = _extract_json_object(
            """```json
            {"verdict":"fake","confidence":1.2,"summary":"This contradicts established facts.","reasoning":["Known falsehood","No evidence"]}
            ```"""
        )
        result = _normalize_llm_payload(payload, "Sample claim")

        self.assertEqual(result["verdict"], "FAKE")
        self.assertEqual(result["label"], "FAKE")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["source_type"], "llm_model_knowledge")
        self.assertEqual(len(result["reasoning"]), 2)

    def test_explainer_includes_llm_fact_check_payload(self):
        llm_fact_check = {
            "enabled": True,
            "available": True,
            "verdict": "UNVERIFIED",
            "label": "UNVERIFIED",
            "confidence": 0.61,
            "summary": "Recent-event claim cannot be verified from model knowledge alone.",
            "reasoning": ["Claim appears time-sensitive"],
            "source_type": "llm_model_knowledge",
            "source_label": "Groq model knowledge (not live news sources)",
            "model": "llama-3.3-70b-versatile",
        }

        explanation = generate_explanation(
            fact_results={
                "evidence_found": False,
                "evidence_strength": "none",
                "news_found": False,
                "wiki_found": False,
                "news_api_available": True,
                "provider_stats": {
                    "configured_count": 4,
                    "hit_count": 0,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [],
                "wiki_results": [],
            },
            semantic_results=[{"match_type": "no_match", "matches": []}],
            final={
                "verdict": "UNVERIFIED",
                "score": 0.57,
                "label": "Unverified — No Supporting Evidence",
                "components": {},
            },
            llm_fact_check=llm_fact_check,
        )

        self.assertEqual(explanation["llm_fact_check"]["verdict"], "UNVERIFIED")
        self.assertTrue(
            any("Groq LLM verdict" in signal["detail"] for signal in explanation["signals"])
        )

    def test_explainer_for_unknown_signal_keeps_verification_details(self):
        explanation = generate_explanation(
            fact_results={
                "evidence_found": False,
                "evidence_strength": "none",
                "news_found": True,
                "wiki_found": False,
                "news_api_available": True,
                "provider_stats": {
                    "configured_count": 4,
                    "hit_count": 1,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [{"total_results": 5}],
                "wiki_results": [],
            },
            semantic_results=[{"match_type": "no_match", "matches": []}],
            final={
                "verdict": "UNVERIFIED",
                "score": 0.58,
                "label": "Unverified — No Supporting Evidence",
                "components": {},
            },
            llm_fact_check={
                "enabled": True,
                "available": True,
                "verdict": "UNVERIFIED",
                "confidence": 0.55,
            },
            claim_context={
                "primary_type": "unknown_signal",
                "confidence": 0.4,
                "reasons": ["Insufficient factual signal for reliable claim typing"],
            },
        )

        self.assertIn("verification was still attempted", explanation["summary"].lower())
        self.assertTrue(any("provider" in reason.lower() for reason in explanation["reasons"]))
        self.assertTrue(any(signal["type"] == "source_counts" for signal in explanation["signals"]))

    def test_strong_llm_real_disagreement_softens_source_only_fake(self):
        fact_results = {
            "evidence_found": False,
            "evidence_strength": "none",
            "news_api_available": True,
            "provider_stats": {
                "configured_count": 4,
                "hit_count": 0,
                "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
            },
            "news_results": [],
            "wiki_results": [],
        }
        semantic_results = [{"match_type": "no_match", "matches": []}]
        llm_fact_check = {
            "enabled": True,
            "available": True,
            "verdict": "REAL",
            "confidence": 0.9,
        }

        final = compute_final_score(
            fact_results=fact_results,
            semantic_results=semantic_results,
            llm_fact_check=llm_fact_check,
        )

        self.assertEqual(final["verdict"], "UNCERTAIN")
        self.assertLess(final["score"], 0.82)
        self.assertGreater(final["components"]["llm_review"]["weight"], 0)

    def test_agreeing_llm_fake_keeps_fake_direction(self):
        fact_results = {
            "evidence_found": False,
            "evidence_strength": "none",
            "news_api_available": True,
            "provider_stats": {
                "configured_count": 4,
                "hit_count": 0,
                "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
            },
            "news_results": [],
            "wiki_results": [],
        }
        semantic_results = [{"match_type": "no_match", "matches": []}]
        llm_fact_check = {
            "enabled": True,
            "available": True,
            "verdict": "FAKE",
            "confidence": 0.9,
        }

        final = compute_final_score(
            fact_results=fact_results,
            semantic_results=semantic_results,
            llm_fact_check=llm_fact_check,
        )

        self.assertIn(final["verdict"], {"LIKELY_FAKE", "FAKE"})
        self.assertGreater(final["score"], 0.75)

    def test_claim_context_detects_evergreen_fact(self):
        context = classify_claims(
            [{"text": "bollywood is a major film industry", "confidence": 0.8}],
            raw_text="bollywood is a major film industry",
        )

        self.assertEqual(context["primary_type"], "evergreen_fact")
        self.assertGreaterEqual(context["confidence"], 0.6)
        self.assertGreater(context["weights"]["llm"], 0.3)

    def test_claim_context_detects_query_claim(self):
        context = classify_claims([], raw_text="Did RBI increase repo rate?")

        self.assertEqual(context["primary_type"], "query_claim")
        self.assertEqual(context["routing"], "query")

    def test_claim_context_detects_opinion_and_prediction(self):
        opinion = classify_claims(
            [{"text": "the government is failing completely", "confidence": 0.7}],
            raw_text="the government is failing completely",
        )
        prediction = classify_claims(
            [{"text": "india will become the largest economy", "confidence": 0.7}],
            raw_text="india will become the largest economy",
        )

        self.assertEqual(opinion["primary_type"], "opinion")
        self.assertEqual(prediction["primary_type"], "predictive_claim")

    def test_dynamic_weighting_favors_sources_for_current_affairs(self):
        current_context = classify_claims(
            [{"text": "rbi increased repo rate", "confidence": 0.8}],
            raw_text="rbi increased repo rate",
        )
        evergreen_context = classify_claims(
            [{"text": "bollywood is a major film industry", "confidence": 0.8}],
            raw_text="bollywood is a major film industry",
        )

        self.assertEqual(current_context["primary_type"], "current_affairs")
        self.assertGreater(current_context["weights"]["source"], evergreen_context["weights"]["source"])
        self.assertGreater(evergreen_context["weights"]["llm"], current_context["weights"]["llm"])

    def test_headline_with_official_and_quits_is_not_unknown_signal(self):
        context = classify_claims(
            [{"text": "top us security official quits, says iran did not pose immediate threat", "confidence": 0.5}],
            raw_text="top us security official quits, says iran did not pose immediate threat",
        )

        self.assertIn(context["primary_type"], {"breaking_news", "current_affairs", "mixed"})
        self.assertNotEqual(context["primary_type"], "unknown_signal")

    def test_lemma_normalization_handles_hiked(self):
        context = classify_claims(
            [{"text": "rbi hiked repo rates", "confidence": 0.8, "original": "RBI hiked repo rates"}],
            raw_text="RBI hiked repo rates",
        )

        self.assertEqual(context["primary_type"], "current_affairs")

    def test_entity_event_headline_uses_original_case(self):
        context = classify_claims(
            [{"text": "apple launched new iphone", "confidence": 0.8, "original": "Apple launched new iPhone"}],
            raw_text="Apple launched new iPhone",
        )

        self.assertIn(context["primary_type"], {"breaking_news", "current_affairs"})
        self.assertNotEqual(context["primary_type"], "unknown_signal")

    def test_maritime_security_headline_is_not_unknown_signal(self):
        text = "India Sends Warships Near Gulf of Oman to Escort Its Fuel Ships"
        context = classify_claims(
            [{"text": text, "confidence": 0.5, "original": text}],
            raw_text=text,
        )

        self.assertIn(context["primary_type"], {"breaking_news", "current_affairs", "mixed"})
        self.assertNotEqual(context["primary_type"], "unknown_signal")
        self.assertGreaterEqual(context["confidence"], 0.6)

    def test_dynamic_copular_clause_does_not_force_evergreen(self):
        context = classify_claims(
            [{"text": "india is growing rapidly", "confidence": 0.8, "original": "India is growing rapidly"}],
            raw_text="India is growing rapidly",
        )

        self.assertNotEqual(context["primary_type"], "evergreen_fact")

    def test_historical_fragment_is_not_unknown_signal(self):
        context = classify_claims(
            [{
                "text": "one of the oldest civilizations indus valley civilization 2500 bce",
                "confidence": 0.5,
                "original": "One of the oldest civilizations (Indus Valley Civilization ~2500 BCE)",
            }],
            raw_text="One of the oldest civilizations (Indus Valley Civilization ~2500 BCE)",
        )

        self.assertEqual(context["primary_type"], "historical_claim")
        self.assertGreater(context["confidence"], 0.6)

    def test_historical_claim_without_sources_stays_unverified(self):
        claim_context = classify_claims(
            [{
                "text": "one of the oldest civilizations indus valley civilization 2500 bce",
                "confidence": 0.5,
                "original": "One of the oldest civilizations (Indus Valley Civilization ~2500 BCE)",
            }],
            raw_text="One of the oldest civilizations (Indus Valley Civilization ~2500 BCE)",
        )
        final = compute_final_score(
            fact_results={
                "evidence_found": False,
                "evidence_strength": "none",
                "news_api_available": True,
                "provider_stats": {
                    "configured_count": 4,
                    "hit_count": 0,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [],
                "wiki_results": [],
            },
            semantic_results=[],
            llm_fact_check={"enabled": True, "available": False, "verdict": "UNVERIFIED"},
            claim_context=claim_context,
        )

        self.assertEqual(final["verdict"], "UNVERIFIED")
        self.assertIn("Historical Claim", final["label"])

    def test_non_factual_routes_return_unverified(self):
        claim_context = classify_claims([], raw_text="Did RBI increase repo rate?")
        final = compute_final_score(
            fact_results={"provider_stats": {}, "news_results": [], "wiki_results": []},
            semantic_results=[],
            llm_fact_check=None,
            claim_context=claim_context,
        )

        self.assertEqual(final["verdict"], "UNVERIFIED")
        self.assertIn("Question", final["label"])

    def test_evergreen_llm_real_can_promote_unverified_to_likely_real(self):
        claim_context = classify_claims(
            [{"text": "bollywood is a major film industry", "confidence": 0.8}],
            raw_text="bollywood is a major film industry",
        )
        final = compute_final_score(
            fact_results={
                "evidence_found": True,
                "evidence_strength": "weak",
                "news_api_available": True,
                "provider_stats": {
                    "configured_count": 4,
                    "hit_count": 2,
                    "configured_providers": ["NewsData.io", "WorldNewsAPI", "NewsMesh", "GNews"],
                },
                "news_results": [{"total_results": 20}],
                "wiki_results": [],
            },
            semantic_results=[{"match_type": "no_match", "matches": []}],
            llm_fact_check={
                "enabled": True,
                "available": True,
                "verdict": "REAL",
                "confidence": 0.95,
            },
            claim_context=claim_context,
        )

        self.assertEqual(final["verdict"], "LIKELY_REAL")
        self.assertIn("Evergreen", final["label"])


if __name__ == "__main__":
    unittest.main()
