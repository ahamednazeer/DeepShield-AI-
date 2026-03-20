COMMON_VERDICT_MAP = {
    "AUTHENTIC": "AUTHENTIC",
    "REAL": "AUTHENTIC",
    "LIKELY_REAL": "AUTHENTIC",
    "SAFE": "AUTHENTIC",
    "LEGITIMATE": "AUTHENTIC",
    "MANIPULATED": "MANIPULATED",
    "FAKE": "MANIPULATED",
    "MISLEADING": "MANIPULATED",
    "UNSAFE": "MANIPULATED",
    "MALICIOUS": "MANIPULATED",
    "PHISHING": "MANIPULATED",
    "SUSPICIOUS": "SUSPICIOUS",
    "LIKELY_FAKE": "SUSPICIOUS",
    "UNCERTAIN": "SUSPICIOUS",
    "UNVERIFIED": "SUSPICIOUS",
    "SPAM": "SUSPICIOUS",
    "RISKY": "SUSPICIOUS",
    "UNKNOWN": "UNKNOWN",
    "ERROR": "UNKNOWN",
}


def normalize_verdict(verdict: str | None) -> str | None:
    if not verdict:
        return verdict
    return COMMON_VERDICT_MAP.get(verdict, verdict)
