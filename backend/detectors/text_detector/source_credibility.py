"""
Source Credibility Module
Evaluates the trustworthiness of a news source based on domain reputation.
"""

from urllib.parse import urlparse

# Curated lists of known sources
TRUSTED_SOURCES = {
    # Major wire services
    "reuters.com", "apnews.com", "afp.com",
    # Major newspapers
    "nytimes.com", "washingtonpost.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "aljazeera.com",
    "thehindu.com", "ndtv.com", "timesofindia.indiatimes.com",
    "hindustantimes.com", "indianexpress.com",
    # Science / research
    "nature.com", "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov",
    "who.int", "cdc.gov", "nasa.gov",
    # Fact-checkers
    "snopes.com", "factcheck.org", "politifact.com",
    "altnews.in", "boomlive.in",
    # Government / official
    "gov.in", "pib.gov.in", "whitehouse.gov",
}

UNTRUSTED_SOURCES = {
    # Known misinformation domains (examples)
    "beforeitsnews.com", "naturalnews.com", "infowars.com",
    "worldnewsdailyreport.com", "yournewswire.com",
    "theonion.com",  # Satire
    "clickhole.com",  # Satire
}

SATIRE_SOURCES = {
    "theonion.com", "clickhole.com", "babylonbee.com",
    "borowitz.com", "fauking.com",
}


def check_credibility(source_url: str = None) -> dict:
    """
    Evaluate source credibility.

    Checks:
    - Domain reputation (trusted/untrusted lists)
    - HTTPS usage
    - Known satire detection
    - Domain age heuristics (TLD analysis)

    Returns dict with score (0-1), rating, and details.
    """
    if not source_url:
        return {
            "score": 0.5,
            "rating": "UNKNOWN",
            "domain": None,
            "details": ["No source URL provided — cannot assess credibility"],
            "is_satire": False,
        }

    try:
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        return {
            "score": 0.3,
            "rating": "LOW",
            "domain": source_url,
            "details": ["Invalid URL format"],
            "is_satire": False,
        }

    score = 0.5  # Neutral baseline
    details = []

    # Check trusted list
    is_trusted = _domain_in_list(domain, TRUSTED_SOURCES)
    if is_trusted:
        score = 0.9
        details.append(f"✅ {domain} is a recognized trusted source")

    # Check untrusted list
    is_untrusted = _domain_in_list(domain, UNTRUSTED_SOURCES)
    if is_untrusted:
        score = 0.1
        details.append(f"⚠️ {domain} is a known unreliable source")

    # Check satire
    is_satire = _domain_in_list(domain, SATIRE_SOURCES)
    if is_satire:
        score = 0.15
        details.append(f"🎭 {domain} is a known satire/parody site")

    # HTTPS check
    uses_https = source_url.startswith("https://")
    if uses_https:
        score = min(score + 0.05, 1.0)
        details.append("🔒 Uses HTTPS")
    else:
        score = max(score - 0.1, 0.0)
        details.append("⚠️ Does not use HTTPS")

    # Suspicious TLD check
    suspicious_tlds = {".xyz", ".top", ".buzz", ".click", ".link", ".info"}
    tld = "." + domain.split(".")[-1] if "." in domain else ""
    if tld in suspicious_tlds:
        score = max(score - 0.2, 0.0)
        details.append(f"⚠️ Suspicious top-level domain: {tld}")

    # Unknown source
    if not is_trusted and not is_untrusted and not is_satire:
        details.append(f"❓ {domain} is not in our known source database")

    # Determine rating
    if score >= 0.8:
        rating = "HIGH"
    elif score >= 0.5:
        rating = "MEDIUM"
    elif score >= 0.3:
        rating = "LOW"
    else:
        rating = "VERY_LOW"

    return {
        "score": round(score, 3),
        "rating": rating,
        "domain": domain,
        "details": details,
        "is_satire": is_satire,
    }


def _domain_in_list(domain: str, domain_set: set) -> bool:
    """Check if domain or any parent domain is in the set."""
    if domain in domain_set:
        return True

    # Check parent domains (e.g., news.bbc.co.uk → bbc.co.uk)
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in domain_set:
            return True

    return False
