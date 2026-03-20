"""
Lightweight NLP helpers for claim typing.
Uses spaCy when available and falls back to regex/token heuristics otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
import threading

try:
    import spacy
except ImportError:  # pragma: no cover
    spacy = None


ENTITY_LABEL_WEIGHTS = {
    "PERSON": 0.9,
    "ORG": 0.9,
    "GPE": 0.85,
    "NORP": 0.75,
    "EVENT": 0.8,
    "LOC": 0.7,
    "FAC": 0.7,
}

FALLBACK_ENTITY_LABELS = {"ENTITY", "ACRONYM"}

COPULAR_VERBS = {"be", "is", "are", "was", "were", "been", "being"}
EVENT_LEMMA_FALLBACKS = {
    "announced": "announce",
    "announce": "announce",
    "confirmed": "confirm",
    "confirm": "confirm",
    "sent": "send",
    "sends": "send",
    "send": "send",
    "says": "say",
    "said": "say",
    "quits": "quit",
    "quit": "quit",
    "resigned": "resign",
    "resign": "resign",
    "approved": "approve",
    "approves": "approve",
    "approve": "approve",
    "passed": "pass",
    "passes": "pass",
    "pass": "pass",
    "arrested": "arrest",
    "arrests": "arrest",
    "launched": "launch",
    "launches": "launch",
    "hiked": "hike",
    "hikes": "hike",
    "boosted": "boost",
    "boosts": "boost",
    "greenlit": "greenlight",
    "greenlights": "greenlight",
    "ruled": "rule",
    "rules": "rule",
    "escorted": "escort",
    "escorts": "escort",
    "escort": "escort",
    "deployed": "deploy",
    "deploys": "deploy",
    "deploy": "deploy",
    "dispatched": "dispatch",
    "dispatches": "dispatch",
    "dispatch": "dispatch",
    "moved": "move",
    "moves": "move",
    "move": "move",
}

RELATIVE_DATE_PATTERNS = (
    r"\blast week\b",
    r"\blate last week\b",
    r"\brecently\b",
    r"\bearlier today\b",
    r"\bthis week\b",
    r"\bthis month\b",
    r"\bnext week\b",
)

CALENDAR_PATTERNS = (
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
)

FALLBACK_ING_TERMS = {
    "growing", "rising", "falling", "declining", "failing", "expanding",
    "changing", "moving", "building", "slowing", "surging", "improving",
}

FALLBACK_ADJECTIVE_TERMS = {
    "strong", "weak", "rapid", "major", "large", "small", "better",
    "worse", "corrupt", "terrible", "great", "bad", "good",
}

FALLBACK_ACTION_LEMMAS = {
    "announce", "confirm", "send", "say", "quit", "resign", "approve", "pass",
    "arrest", "launch", "hike", "boost", "greenlight", "rule", "close", "lose",
    "kill", "die", "strike", "collapse", "surge", "fall", "rise", "declare",
    "reveal", "report", "sign", "enact", "increase", "decrease", "raise", "cut",
    "escort", "deploy", "dispatch", "move", "attack", "target", "seize",
    "detain", "evacuate", "intercept", "warn", "threaten",
}

_SPACY_MODEL_NAME = "en_core_web_sm"
_DOWNLOAD_LOCK = threading.Lock()


@dataclass
class NLPView:
    original_text: str
    lower_text: str
    tokens: list[str]
    lemmas: list[str]
    pos_tags: list[str]
    entities: list[dict]
    parser_available: bool
    spacy_available: bool

    @property
    def lemma_set(self) -> set[str]:
        return set(self.lemmas)

    @property
    def token_set(self) -> set[str]:
        return set(self.tokens)


def build_nlp_view(text: str) -> NLPView:
    """Analyze text with spaCy when available, or a regex fallback otherwise."""
    text = (text or "").strip()
    if not text:
        return NLPView(
            original_text="",
            lower_text="",
            tokens=[],
            lemmas=[],
            pos_tags=[],
            entities=[],
            parser_available=False,
            spacy_available=False,
        )

    nlp = _get_spacy_model()
    if nlp is not None:
        doc = nlp(text)
        tokens = [token.text.lower() for token in doc if not token.is_space and not token.is_punct]
        lemmas = [_normalize_lemma(token.lemma_ or token.text) for token in doc if not token.is_space and not token.is_punct]
        pos_tags = [token.pos_ or "" for token in doc if not token.is_space and not token.is_punct]
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        parser_available = any(tag for tag in pos_tags)
        return NLPView(
            original_text=text,
            lower_text=text.lower(),
            tokens=tokens,
            lemmas=lemmas,
            pos_tags=pos_tags,
            entities=entities,
            parser_available=parser_available,
            spacy_available=True,
        )

    tokens = re.findall(r"[A-Za-z0-9']+", text)
    lower_tokens = [token.lower() for token in tokens]
    lemmas = [_normalize_lemma(token) for token in lower_tokens]
    entities = _fallback_entities(text)
    return NLPView(
        original_text=text,
        lower_text=text.lower(),
        tokens=lower_tokens,
        lemmas=lemmas,
        pos_tags=[],
        entities=entities,
        parser_available=False,
        spacy_available=False,
    )


def contains_term(view: NLPView, term: str) -> bool:
    """Match terms against raw text and lemmas."""
    term = term.lower().strip()
    if not term:
        return False

    term_parts = [_normalize_lemma(part) for part in re.findall(r"[A-Za-z0-9']+", term)]
    if not term_parts:
        return False

    if len(term_parts) == 1:
        target = term_parts[0]
        if re.search(rf"\b{re.escape(term)}\b", view.lower_text):
            return True
        return target in view.lemma_set or target in view.token_set

    if term in view.lower_text:
        return True

    return _contains_ngram(view.lemmas, term_parts) or _contains_ngram(view.tokens, term_parts)


def count_recency_markers(view: NLPView) -> int:
    """Count explicit date or recency markers."""
    count = 0
    for pattern in RELATIVE_DATE_PATTERNS + CALENDAR_PATTERNS:
        count += len(re.findall(pattern, view.lower_text, flags=re.IGNORECASE))
    return count


def entity_signal(view: NLPView) -> float:
    """Compute a named-entity signal from spaCy entities or fallback capitalization."""
    signal = 0.0
    for entity in view.entities:
        label = entity.get("label", "")
        signal += ENTITY_LABEL_WEIGHTS.get(label, 0.5 if label in FALLBACK_ENTITY_LABELS else 0.0)
    return min(signal, 3.2)


def has_entity_event_pattern(view: NLPView, event_lemmas: set[str]) -> bool:
    """Detect the common 'entity + event verb' structure."""
    if not view.entities:
        return False
    return any(lemma in event_lemmas for lemma in view.lemmas)


def has_noncopular_verb(view: NLPView) -> bool:
    """Detect an action verb even when it is outside the curated event-verb list."""
    if view.spacy_available and view.pos_tags:
        return any(
            pos in {"VERB", "AUX"} and lemma not in COPULAR_VERBS
            for lemma, pos in zip(view.lemmas, view.pos_tags)
        )

    return any(lemma in FALLBACK_ACTION_LEMMAS for lemma in view.lemmas)


def is_dynamic_copular_clause(view: NLPView) -> bool:
    """
    Detect 'is/are + adjective or ongoing action' clauses that should not be treated
    as stable evergreen facts.
    """
    if view.spacy_available and view.pos_tags:
        for idx, lemma in enumerate(view.lemmas):
            if lemma not in COPULAR_VERBS:
                continue
            if idx + 1 >= len(view.lemmas):
                continue
            next_lemma = view.lemmas[idx + 1]
            next_pos = view.pos_tags[idx + 1]
            if next_pos in {"ADJ", "ADV", "VERB"}:
                if next_lemma.endswith("ing") or next_lemma in FALLBACK_ING_TERMS or next_pos == "ADJ":
                    return True
        return False

    tokens = view.tokens
    for idx, token in enumerate(tokens[:-1]):
        if token not in COPULAR_VERBS:
            continue
        nxt = tokens[idx + 1]
        if nxt in FALLBACK_ING_TERMS or nxt.endswith("ing") or nxt in FALLBACK_ADJECTIVE_TERMS:
            return True
    return False


def _contains_ngram(sequence: list[str], term_parts: list[str]) -> bool:
    if len(term_parts) > len(sequence):
        return False
    for idx in range(len(sequence) - len(term_parts) + 1):
        if sequence[idx:idx + len(term_parts)] == term_parts:
            return True
    return False


def _normalize_lemma(token: str) -> str:
    token = (token or "").lower().strip()
    if not token:
        return ""
    if token in EVENT_LEMMA_FALLBACKS:
        return EVENT_LEMMA_FALLBACKS[token]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _fallback_entities(text: str) -> list[dict]:
    entities = []
    seen = set()

    for match in re.finditer(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b", text):
        value = match.group(0).strip()
        if value.lower() in {"the", "a", "an"}:
            continue
        if value in seen:
            continue
        seen.add(value)
        label = "ACRONYM" if value.isupper() or len(value.split()) == 1 and value[:1].isupper() and value[1:].isupper() else "ENTITY"
        entities.append({"text": value, "label": label})

    return entities


@lru_cache(maxsize=1)
def _get_spacy_model():
    if spacy is None:  # pragma: no cover
        return None
    try:
        return spacy.load(_SPACY_MODEL_NAME)
    except Exception:  # pragma: no cover
        with _DOWNLOAD_LOCK:
            try:
                return spacy.load(_SPACY_MODEL_NAME)
            except Exception:
                pass

            try:
                from spacy.cli import download as spacy_download

                spacy_download(_SPACY_MODEL_NAME)
                return spacy.load(_SPACY_MODEL_NAME)
            except Exception:
                pass
        return None
