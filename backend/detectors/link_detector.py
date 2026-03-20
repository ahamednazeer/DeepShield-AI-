import asyncio
import ipaddress
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from config import (
    LINK_PROVIDER_POLL_ATTEMPTS,
    LINK_PROVIDER_POLL_INTERVAL_SECONDS,
    LINK_PROVIDER_TIMEOUT_SECONDS,
    URLSCAN_API_KEY,
    URLSCAN_VISIBILITY,
    VIRUSTOTAL_API_KEY,
)

SHORTENER_DOMAINS = {
    "bit.ly",
    "cutt.ly",
    "is.gd",
    "ow.ly",
    "rb.gy",
    "shorturl.at",
    "t.co",
    "tiny.cc",
    "tinyurl.com",
    "url.ie",
}

SUSPICIOUS_TLDS = {
    ".buzz",
    ".cam",
    ".click",
    ".club",
    ".fit",
    ".gq",
    ".icu",
    ".link",
    ".live",
    ".mom",
    ".monster",
    ".online",
    ".rest",
    ".ru",
    ".shop",
    ".support",
    ".top",
    ".vip",
    ".work",
    ".world",
    ".xyz",
}

SUSPICIOUS_KEYWORDS = {
    "account",
    "bank",
    "billing",
    "bonus",
    "confirm",
    "crypto",
    "gift",
    "invoice",
    "login",
    "lottery",
    "password",
    "payment",
    "prize",
    "recover",
    "reset",
    "reward",
    "secure",
    "signin",
    "unlock",
    "update",
    "urgent",
    "verify",
    "wallet",
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _signal(source: str, label: str, severity: str, weight: float, details: dict[str, Any] | None = None) -> dict:
    return {
        "source": source,
        "label": label,
        "severity": severity,
        "weight": round(weight, 3),
        "details": details or {},
    }


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item and item not in output:
            output.append(item)
    return output


def _clean_error_message(message: str) -> str:
    return " ".join((message or "").split())[:240]


def _extract_tld(hostname: str) -> str:
    parts = hostname.split(".")
    if len(parts) < 2:
        return ""
    return f".{parts[-1]}"


def _host_flags(hostname: str) -> dict[str, bool]:
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return {"is_ip": False, "is_private": True, "is_localhost": True}

    try:
        ip = ipaddress.ip_address(lowered)
        return {
            "is_ip": True,
            "is_private": bool(
                ip.is_private
                or ip.is_loopback
                or ip.is_reserved
                or ip.is_link_local
                or ip.is_multicast
            ),
            "is_localhost": bool(ip.is_loopback),
        }
    except ValueError:
        return {"is_ip": False, "is_private": False, "is_localhost": False}


def normalize_url(raw_url: str) -> dict[str, Any]:
    candidate = (raw_url or "").strip()
    if not candidate:
        raise ValueError("URL cannot be empty")
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported")

    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if not hostname:
        raise ValueError("URL host is required")

    try:
        ascii_host = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        ascii_host = hostname

    port = parsed.port
    netloc = ascii_host
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    if port and not default_port:
        netloc = f"{netloc}:{port}"

    path = parsed.path or "/"
    normalized_url = urlunparse((scheme, netloc, path, "", parsed.query, ""))
    flags = _host_flags(ascii_host)
    return {
        "input_url": raw_url.strip(),
        "normalized_url": normalized_url,
        "scheme": scheme,
        "hostname": ascii_host,
        "display_host": hostname,
        "path": path,
        "query": parsed.query or "",
        "has_credentials": bool(parsed.username or parsed.password),
        **flags,
    }


def run_local_heuristics(url_info: dict[str, Any]) -> dict[str, Any]:
    hostname = url_info["hostname"]
    url = url_info["normalized_url"]
    path_and_query = f"{url_info['path']}?{url_info['query']}".lower()
    segments = hostname.split(".")
    query_pairs = [pair for pair in url_info["query"].split("&") if pair]

    score = 0.0
    categories: list[str] = []
    signals: list[dict[str, Any]] = []

    def add(weight: float, label: str, severity: str, category: str | None = None, details: dict[str, Any] | None = None):
        nonlocal score
        score = _clamp(score + weight, 0.0, 0.95)
        signals.append(_signal("local", label, severity, weight, details))
        if category and category not in categories:
            categories.append(category)

    if url_info["scheme"] == "http":
        add(0.08, "Uses insecure HTTP instead of HTTPS", "medium", "unsafe")

    if url_info["has_credentials"]:
        add(0.2, "URL embeds user credentials", "high", "phishing")

    if "@" in url:
        add(0.18, "URL contains @ obfuscation", "high", "phishing")

    if url_info["is_localhost"] or url_info["is_private"]:
        add(0.65, "Targets localhost or a private IP range", "high", "unsafe")

    if url_info["is_ip"]:
        add(0.28, "Host is a raw IP address", "high", "unsafe")

    if hostname.startswith("xn--") or ".xn--" in hostname:
        add(0.28, "Host uses punycode and may be homograph-based", "high", "phishing")

    if _extract_tld(hostname) in SUSPICIOUS_TLDS:
        add(0.12, "Top-level domain is commonly abused", "medium", "suspicious_tld")

    if hostname in SHORTENER_DOMAINS or any(hostname.endswith(f".{domain}") for domain in SHORTENER_DOMAINS):
        add(0.14, "URL shortener detected", "medium", "shortener")

    if len(segments) > 4:
        add(0.08, "Excessive subdomain depth", "medium", "obfuscation", {"subdomains": len(segments) - 2})

    if len(url) > 120:
        add(0.08, "Unusually long URL", "medium", "obfuscation", {"length": len(url)})

    if len(query_pairs) > 8:
        add(0.08, "Large number of query parameters", "medium", "tracking", {"query_params": len(query_pairs)})

    if url.count("%") >= 6:
        add(0.08, "Heavy percent-encoding detected", "medium", "obfuscation")

    digit_ratio = sum(char.isdigit() for char in hostname) / max(len(hostname), 1)
    if digit_ratio >= 0.25:
        add(0.08, "Host contains an unusual amount of digits", "medium", "obfuscation")

    if hostname.count("-") >= 3:
        add(0.08, "Host contains multiple hyphen separators", "medium", "obfuscation")

    keyword_hits = sorted({keyword for keyword in SUSPICIOUS_KEYWORDS if keyword in path_and_query or keyword in hostname})
    if keyword_hits:
        weight = min(0.22, 0.08 + (0.02 * len(keyword_hits)))
        add(weight, "Sensitive or phishing-style keywords detected", "high", "phishing", {"keywords": keyword_hits})

    if not signals:
        signals.append(_signal("local", "No strong local risk indicators detected", "low", 0.0))

    return {
        "risk_score": round(score, 4),
        "signals": signals,
        "categories": categories,
        "skip_external": bool(url_info["is_private"] or url_info["is_localhost"]),
    }


async def _poll_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.request(method, url, headers=headers, json=json, data=data)
    response.raise_for_status()
    return response.json()


async def lookup_virustotal(normalized_url: str) -> dict[str, Any]:
    if not VIRUSTOTAL_API_KEY:
        return {"summary": {"status": "disabled", "reason": "VIRUSTOTAL_API_KEY is not configured"}, "signals": []}

    headers = {"x-apikey": VIRUSTOTAL_API_KEY, "accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=LINK_PROVIDER_TIMEOUT_SECONDS, follow_redirects=True) as client:
            submission = await _poll_json(
                client,
                "POST",
                "https://www.virustotal.com/api/v3/urls",
                headers=headers,
                data={"url": normalized_url},
            )
            analysis_id = ((submission.get("data") or {}).get("id")) if isinstance(submission, dict) else None
            analysis_payload: dict[str, Any] = {}

            for attempt in range(LINK_PROVIDER_POLL_ATTEMPTS):
                if not analysis_id:
                    break
                analysis_response = await _poll_json(
                    client,
                    "GET",
                    f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                    headers=headers,
                )
                analysis_payload = (analysis_response.get("data") or {}) if isinstance(analysis_response, dict) else {}
                status = ((analysis_payload.get("attributes") or {}).get("status")) if analysis_payload else None
                if status == "completed" or attempt == LINK_PROVIDER_POLL_ATTEMPTS - 1:
                    break
                await asyncio.sleep(LINK_PROVIDER_POLL_INTERVAL_SECONDS)

        attributes = analysis_payload.get("attributes") or {}
        analysis_status = attributes.get("status") or "pending"
        if analysis_status != "completed":
            return {
                "summary": {
                    "status": "pending",
                    "analysis_id": analysis_payload.get("id") or analysis_id,
                    "analysis_status": analysis_status,
                },
                "signals": [],
            }
        stats = attributes.get("stats") or {}
        results = attributes.get("results") or {}
        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        harmless = int(stats.get("harmless", 0) or 0)
        undetected = int(stats.get("undetected", 0) or 0)
        total = malicious + suspicious + harmless + undetected
        risk_score = 0.0
        if total:
            risk_score = _clamp((malicious + (0.6 * suspicious)) / total)

        detections = []
        for engine, engine_result in results.items():
            category = (engine_result or {}).get("category")
            if category not in {"malicious", "suspicious"}:
                continue
            detections.append(
                {
                    "engine": engine,
                    "category": category,
                    "result": (engine_result or {}).get("result"),
                    "method": (engine_result or {}).get("method"),
                }
            )
            if len(detections) >= 8:
                break

        provider_signals: list[dict[str, Any]] = []
        if malicious:
            provider_signals.append(
                _signal(
                    "virustotal",
                    f"VirusTotal flagged the URL as malicious with {malicious} positive engines",
                    "high",
                    max(0.2, risk_score),
                    {"stats": stats},
                )
            )
        elif suspicious:
            provider_signals.append(
                _signal(
                    "virustotal",
                    f"VirusTotal reported suspicious detections from {suspicious} engines",
                    "medium",
                    max(0.12, risk_score),
                    {"stats": stats},
                )
            )

        return {
            "risk_score": round(risk_score, 4),
            "malicious_hits": malicious,
            "suspicious_hits": suspicious,
            "categories": [category for category in ("malicious" if malicious else None, "suspicious" if suspicious else None) if category],
            "signals": provider_signals,
            "summary": {
                "status": "completed",
                "analysis_id": analysis_payload.get("id") or analysis_id,
                "analysis_status": analysis_status,
                "stats": stats,
                "detections": detections,
                "risk_score": round(risk_score, 4),
            },
        }
    except httpx.HTTPError as exc:
        return {
            "summary": {
                "status": "error",
                "reason": _clean_error_message(str(exc)),
            },
            "signals": [],
        }


def _extract_urlscan_redirect_chain(payload: dict[str, Any], submitted_url: str) -> list[str]:
    task = payload.get("task") or {}
    page = payload.get("page") or {}
    chain = [task.get("url"), page.get("url")]
    if page.get("redirected"):
        lists = payload.get("lists") or {}
        for candidate in lists.get("urls") or []:
            chain.append(candidate)
            if len(chain) >= 6:
                break
    chain.append(submitted_url)
    return _dedupe(chain)


async def lookup_urlscan(normalized_url: str) -> dict[str, Any]:
    if not URLSCAN_API_KEY:
        return {"summary": {"status": "disabled", "reason": "URLSCAN_API_KEY is not configured"}, "signals": []}

    headers = {"API-Key": URLSCAN_API_KEY, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=LINK_PROVIDER_TIMEOUT_SECONDS, follow_redirects=True) as client:
            submission = await _poll_json(
                client,
                "POST",
                "https://urlscan.io/api/v1/scan/",
                headers=headers,
                json={"url": normalized_url, "visibility": URLSCAN_VISIBILITY},
            )
            uuid = submission.get("uuid")
            result_endpoint = submission.get("api") or (f"https://urlscan.io/api/v1/result/{uuid}/" if uuid else None)
            result_payload: dict[str, Any] = {}

            for attempt in range(LINK_PROVIDER_POLL_ATTEMPTS):
                if not result_endpoint:
                    break
                response = await client.get(result_endpoint, headers={"API-Key": URLSCAN_API_KEY})
                if response.status_code == 404:
                    if attempt == LINK_PROVIDER_POLL_ATTEMPTS - 1:
                        break
                    await asyncio.sleep(LINK_PROVIDER_POLL_INTERVAL_SECONDS)
                    continue
                response.raise_for_status()
                result_payload = response.json()
                break

        if not result_payload:
            return {
                "summary": {
                    "status": "pending",
                    "uuid": submission.get("uuid"),
                    "visibility": submission.get("visibility"),
                    "scan_result": submission.get("result"),
                    "message": submission.get("message"),
                },
                "signals": [],
                "redirect_chain": [normalized_url],
                "page_metadata": {},
            }

        verdicts = result_payload.get("verdicts") or {}
        urlscan_verdict = verdicts.get("urlscan") or {}
        score_value = float(urlscan_verdict.get("score") or 0)
        risk_score = _clamp(max(score_value, 0.0) / 100.0)
        categories = list(urlscan_verdict.get("categories") or [])
        brands = list(urlscan_verdict.get("brands") or [])
        page = result_payload.get("page") or {}
        meta = result_payload.get("meta") or {}
        downloads = (((meta.get("processors") or {}).get("download") or {}).get("data")) or []
        redirect_chain = _extract_urlscan_redirect_chain(result_payload, normalized_url)

        provider_signals: list[dict[str, Any]] = []
        if score_value >= 75:
            provider_signals.append(
                _signal(
                    "urlscan",
                    f"urlscan assigned a high-risk score of {int(score_value)}",
                    "high",
                    max(0.25, risk_score),
                    {"categories": categories},
                )
            )
        elif score_value >= 20 or categories:
            provider_signals.append(
                _signal(
                    "urlscan",
                    f"urlscan flagged the page as suspicious ({', '.join(categories) or 'score-only'})",
                    "medium",
                    max(0.12, risk_score),
                    {"categories": categories},
                )
            )

        if downloads:
            provider_signals.append(
                _signal(
                    "urlscan",
                    "The page triggered file downloads during the scan",
                    "high",
                    0.16,
                    {"download_count": len(downloads)},
                )
            )

        return {
            "risk_score": round(risk_score, 4),
            "score_value": score_value,
            "categories": categories,
            "signals": provider_signals,
            "final_url": page.get("url"),
            "redirect_chain": redirect_chain,
            "page_metadata": {
                "title": page.get("title"),
                "status": page.get("status"),
                "domain": page.get("domain"),
                "server": page.get("server"),
                "country": page.get("country"),
                "ip": page.get("ip"),
                "redirected": page.get("redirected"),
            },
            "summary": {
                "status": "completed" if result_payload else "pending",
                "uuid": submission.get("uuid"),
                "visibility": submission.get("visibility"),
                "scan_result": submission.get("result"),
                "message": submission.get("message"),
                "risk_score": round(risk_score, 4),
                "score": score_value,
                "categories": categories,
                "brands": brands,
                "page": {
                    "title": page.get("title"),
                    "url": page.get("url"),
                    "status": page.get("status"),
                    "domain": page.get("domain"),
                },
                "downloads": len(downloads),
            },
        }
    except httpx.HTTPError as exc:
        return {
            "summary": {
                "status": "error",
                "reason": _clean_error_message(str(exc)),
            },
            "signals": [],
        }


def _combine_scores(components: list[tuple[float, float | None]]) -> float:
    weighted_total = 0.0
    applied_weight = 0.0
    for weight, score in components:
        if score is None:
            continue
        weighted_total += weight * score
        applied_weight += weight
    if not applied_weight:
        return 0.0
    return _clamp(weighted_total / applied_weight)


def _provider_status(summary: dict[str, Any] | None) -> str:
    payload = summary or {}
    status = str(payload.get("status") or "unknown").lower()
    analysis_status = str(payload.get("analysis_status") or "").lower()
    if status == "completed" and analysis_status and analysis_status != "completed":
        return "pending"
    return status


def _provider_is_enabled(summary: dict[str, Any] | None) -> bool:
    return _provider_status(summary) not in {"disabled", "skipped"}


def _provider_is_completed(summary: dict[str, Any] | None) -> bool:
    return _provider_status(summary) == "completed"


def _provider_is_pending(summary: dict[str, Any] | None) -> bool:
    return _provider_status(summary) == "pending"


def summarize_provider_gate(provider_summary: dict[str, Any], *, skip_external: bool) -> dict[str, Any]:
    vt_summary = provider_summary.get("virustotal") or {}
    urlscan_summary = provider_summary.get("urlscan") or {}
    enabled_summaries = [summary for summary in (vt_summary, urlscan_summary) if _provider_is_enabled(summary)]
    completed_summaries = [summary for summary in enabled_summaries if _provider_is_completed(summary)]

    if skip_external:
        return {
            "ready": True,
            "pending": False,
            "incomplete": False,
            "has_completed_provider": False,
        }

    pending = any(_provider_is_pending(summary) for summary in enabled_summaries)
    incomplete = any(_provider_status(summary) != "completed" for summary in enabled_summaries)
    return {
        "ready": bool(enabled_summaries) and len(completed_summaries) == len(enabled_summaries),
        "pending": pending,
        "incomplete": incomplete and not pending,
        "has_completed_provider": bool(completed_summaries),
    }


def resolve_link_outcome(
    provider_summary: dict[str, Any],
    *,
    skip_external: bool,
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    vt_summary = provider_summary.get("virustotal") or {}
    urlscan_summary = provider_summary.get("urlscan") or {}
    gate = summarize_provider_gate(provider_summary, skip_external=skip_external)

    vt_risk = vt_summary.get("risk_score") if _provider_is_completed(vt_summary) else None
    urlscan_risk = urlscan_summary.get("risk_score") if _provider_is_completed(urlscan_summary) else None
    combined_score = _combine_scores(
        [
            (0.55, vt_risk),
            (0.45, urlscan_risk),
        ]
    )
    categories = _dedupe(list(urlscan_summary.get("categories") or []))
    vt_stats = vt_summary.get("stats") or {}

    hard_block = (
        skip_external
        or int(vt_stats.get("malicious", 0) or 0) > 0
        or "phishing" in categories
        or "malware" in categories
        or float(urlscan_summary.get("score") or 0) >= 75
    )
    spam_like = "spam" in categories or "bulk" in categories

    if not gate["ready"]:
        return {
            "status": "processing" if gate["pending"] else "incomplete",
            "verdict": "UNKNOWN",
            "raw_verdict": "PENDING_PROVIDER_RESULTS" if gate["pending"] else "PROVIDER_INCOMPLETE",
            "risk_score": None,
            "signals": signals,
            "categories": categories,
        }

    if hard_block:
        raw_verdict = "PHISHING" if "phishing" in categories else "UNSAFE"
        verdict = "MANIPULATED"
        combined_score = max(combined_score, 0.72)
    elif not gate["has_completed_provider"]:
        raw_verdict = "UNKNOWN"
        verdict = "UNKNOWN"
    elif combined_score >= 0.65:
        raw_verdict = "UNSAFE"
        verdict = "MANIPULATED"
    elif spam_like or combined_score >= 0.35 or int(vt_stats.get("suspicious", 0) or 0) > 0:
        raw_verdict = "SPAM" if spam_like else "RISKY"
        verdict = "SUSPICIOUS"
    else:
        raw_verdict = "SAFE"
        verdict = "AUTHENTIC"

    return {
        "status": "completed",
        "verdict": verdict,
        "raw_verdict": raw_verdict,
        "risk_score": round(_clamp(combined_score), 4),
        "signals": signals,
        "categories": categories,
    }


async def analyze_link(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    url_info = normalize_url(url)
    skip_external = bool(url_info["is_private"] or url_info["is_localhost"])

    if skip_external:
        vt_result = {"summary": {"status": "skipped", "reason": "External lookups are blocked for private or localhost targets"}, "signals": []}
        urlscan_result = {"summary": {"status": "skipped", "reason": "External lookups are blocked for private or localhost targets"}, "signals": []}
    else:
        vt_result, urlscan_result = await asyncio.gather(
            lookup_virustotal(url_info["normalized_url"]),
            lookup_urlscan(url_info["normalized_url"]),
        )

    final_url = urlscan_result.get("final_url") or url_info["normalized_url"]
    signals = sorted(
        [
            *(
                [
                    _signal(
                        "system",
                        "Private or localhost targets are not sent to external scanners",
                        "high",
                        0.8,
                    )
                ]
                if skip_external
                else []
            ),
            *(vt_result.get("signals", []) or []),
            *(urlscan_result.get("signals", []) or []),
        ],
        key=lambda item: (item.get("weight", 0.0), item.get("severity", "")),
        reverse=True,
    )
    redirect_chain = _dedupe(
        [url_info["normalized_url"], *(urlscan_result.get("redirect_chain", []) or []), final_url]
    )

    provider_summary = {
        "virustotal": vt_result.get("summary", {}),
        "urlscan": urlscan_result.get("summary", {}),
    }
    resolved = resolve_link_outcome(
        provider_summary,
        skip_external=skip_external,
        signals=signals,
    )

    page_metadata = urlscan_result.get("page_metadata") or {}

    return {
        "input_url": url_info["input_url"],
        "normalized_url": url_info["normalized_url"],
        "final_url": final_url,
        "domain": page_metadata.get("domain") or url_info["hostname"],
        "status": resolved["status"],
        "risk_score": resolved["risk_score"],
        "verdict": resolved["verdict"],
        "raw_verdict": resolved["raw_verdict"],
        "signals": resolved["signals"],
        "provider_summary": provider_summary,
        "redirect_chain": redirect_chain,
        "page_metadata": page_metadata,
        "processing_time": round(time.perf_counter() - started, 2),
    }
