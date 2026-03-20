"""
Groq-backed fact-check helper.
Runs a model-knowledge-only classification that stays separate from live news verification.
"""

import json
import re

import httpx

try:
    from config import GROQ_API_KEY, GROQ_MODEL
except ModuleNotFoundError:
    from backend.config import GROQ_API_KEY, GROQ_MODEL

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
ALLOWED_VERDICTS = {"REAL", "FAKE", "UNVERIFIED"}


async def run_llm_fact_check(input_text: str, claims: list) -> dict:
    """Classify the input using Groq model knowledge only."""
    checked_claim = _build_checked_claim(input_text, claims)
    if not GROQ_API_KEY:
        return _unavailable_response(
            checked_claim=checked_claim,
            message="Groq fact check is not configured.",
            enabled=False,
        )

    request_payload = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_completion_tokens": 350,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a cautious fact-check assistant. "
                    "Use only your general model knowledge. "
                    "Do not assume access to live news, browsing, or external tools. "
                    "If the claim is time-sensitive, ambiguous, opinion-based, or uncertain, return UNVERIFIED. "
                    "Respond with JSON only using the keys verdict, confidence, summary, reasoning."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Classify the following claim or text as REAL, FAKE, or UNVERIFIED.\n"
                    "REAL means broadly consistent with established knowledge.\n"
                    "FAKE means clearly false or contradicting established knowledge.\n"
                    "UNVERIFIED means uncertain, ambiguous, or likely dependent on recent events.\n"
                    "Return confidence as a number from 0 to 1 and reasoning as a short list.\n\n"
                    f"Claim/Text:\n{checked_claim}"
                ),
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )

        if response.status_code != 200:
            return _unavailable_response(
                checked_claim=checked_claim,
                message=f"Groq fact check unavailable ({response.status_code}).",
                enabled=True,
            )

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json_object(content)
        normalized = _normalize_llm_payload(parsed, checked_claim)
        normalized["enabled"] = True
        normalized["available"] = True
        normalized["model"] = data.get("model") or GROQ_MODEL
        return normalized

    except Exception as exc:
        return _unavailable_response(
            checked_claim=checked_claim,
            message=f"Groq fact check unavailable: {exc}",
            enabled=True,
        )


def _build_checked_claim(input_text: str, claims: list) -> str:
    """Build a stable LLM prompt payload from extracted claims and raw text."""
    claim_texts = [claim.get("text", "").strip() for claim in claims if claim.get("text")]
    if len(claim_texts) == 1:
        return claim_texts[0][:500]
    if claim_texts:
        return "\n".join(f"- {claim[:300]}" for claim in claim_texts[:5])
    return (input_text or "").strip()[:500]


def _extract_json_object(content: str) -> dict:
    """Parse the first JSON object in a model response."""
    if isinstance(content, dict):
        return content

    text = (content or "").strip()
    if not text:
        return {}

    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _normalize_llm_payload(payload: dict, checked_claim: str) -> dict:
    """Normalize arbitrary model JSON into the UI/API payload shape."""
    verdict = str(payload.get("verdict", "UNVERIFIED")).strip().upper()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "UNVERIFIED"

    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = round(min(max(confidence, 0.0), 1.0), 4)

    reasoning = payload.get("reasoning", [])
    if isinstance(reasoning, str):
        reasoning = [reasoning]
    if not isinstance(reasoning, list):
        reasoning = []
    reasoning = [str(item).strip() for item in reasoning if str(item).strip()][:3]

    summary = str(payload.get("summary") or _default_summary(verdict)).strip()

    return {
        "enabled": True,
        "available": True,
        "verdict": verdict,
        "label": verdict,
        "confidence": confidence,
        "summary": summary[:240],
        "reasoning": reasoning,
        "checked_claim": checked_claim,
        "source_type": "llm_model_knowledge",
        "source_label": "Groq model knowledge (not live news sources)",
        "model": GROQ_MODEL,
    }


def _default_summary(verdict: str) -> str:
    if verdict == "REAL":
        return "The claim appears consistent with established model knowledge."
    if verdict == "FAKE":
        return "The claim appears inconsistent with established model knowledge."
    return "The model could not verify the claim confidently without live evidence."


def _unavailable_response(checked_claim: str, message: str, enabled: bool) -> dict:
    return {
        "enabled": enabled,
        "available": False,
        "verdict": "UNVERIFIED",
        "label": "UNVERIFIED",
        "confidence": None,
        "summary": message,
        "reasoning": [],
        "checked_claim": checked_claim,
        "source_type": "llm_model_knowledge",
        "source_label": "Groq model knowledge (not live news sources)",
        "model": GROQ_MODEL if enabled else None,
    }
