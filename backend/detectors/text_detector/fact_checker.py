"""
Multi-provider fact verification module.
Checks claims against NewsData.io, WorldNewsAPI, NewsMesh, GNews, and Wikipedia.
"""

import asyncio
from urllib.parse import urlparse

import httpx

try:
    from config import (
        GNEWS_API_KEY,
        NEWSDATA_API_KEY,
        NEWSMESH_API_KEY,
        WORLDNEWS_API_KEY,
    )
except ModuleNotFoundError:
    from backend.config import (
        GNEWS_API_KEY,
        NEWSDATA_API_KEY,
        NEWSMESH_API_KEY,
        WORLDNEWS_API_KEY,
    )

NEWSDATA_URL = "https://newsdata.io/api/1/latest"
WORLDNEWS_URL = "https://api.worldnewsapi.com/search-news"
NEWSMESH_URL = "https://api.newsmesh.co/v1/search"
GNEWS_URL = "https://gnews.io/api/v4/search"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

PROVIDER_LABELS = {
    "newsdata": "NewsData.io",
    "worldnews": "WorldNewsAPI",
    "newsmesh": "NewsMesh",
    "gnews": "GNews",
}


async def check_facts(queries: list, claims: list) -> dict:
    """
    Verify claims using multiple news providers plus Wikipedia.

    Returns aggregated per-claim news results for semantic matching, alongside
    provider-level detail for explanation and scoring.
    """
    news_results = []
    wiki_results = []
    provider_results = {name: [] for name in _configured_provider_names()}
    hit_providers = set()
    available_providers = set()
    wiki_available = False

    async with httpx.AsyncClient(timeout=20.0) as client:
        unique_queries = _dedupe_queries(queries)[:5]

        for query in unique_queries:
            claim_index = query["claim_index"]
            search_text = query["query"]

            provider_payloads, wiki = await asyncio.gather(
                _query_all_providers(client, search_text),
                _check_wikipedia(client, search_text),
            )

            combined_articles = []
            combined_total = 0
            claim_hit_providers = []

            for provider_name, payload in provider_payloads.items():
                normalized = {
                    "claim_index": claim_index,
                    "query": search_text,
                    "articles": payload.get("articles", []),
                    "total_results": payload.get("total_results", 0),
                    "found": payload.get("found", False),
                    "available": payload.get("available", False),
                }
                provider_results[provider_name].append(normalized)

                if normalized["available"]:
                    available_providers.add(provider_name)
                if normalized["found"]:
                    hit_providers.add(provider_name)
                    claim_hit_providers.append(provider_name)

                combined_articles.extend(normalized["articles"])
                combined_total += normalized["total_results"]

            news_results.append({
                "claim_index": claim_index,
                "query": search_text,
                "articles": combined_articles[:12],
                "total_results": combined_total,
                "found": bool(claim_hit_providers),
                "hit_providers": claim_hit_providers,
            })

            wiki_results.append({
                "claim_index": claim_index,
                "query": search_text,
                "results": wiki.get("results", []),
                "found": len(wiki.get("results", [])) > 0,
                "available": wiki.get("available", False),
            })
            if wiki.get("available", False):
                wiki_available = True

    provider_stats = {
        "configured_providers": [PROVIDER_LABELS[name] for name in _configured_provider_names()],
        "configured_count": len(_configured_provider_names()),
        "available_providers": [PROVIDER_LABELS[name] for name in sorted(available_providers)],
        "available_count": len(available_providers),
        "hit_providers": [PROVIDER_LABELS[name] for name in sorted(hit_providers)],
        "hit_count": len(hit_providers),
    }

    news_found = any(result.get("found", False) for result in news_results)
    wiki_found = any(result.get("found", False) for result in wiki_results)
    evidence_strength = _assess_evidence_strength(news_results, wiki_results, provider_stats)

    return {
        "news_results": news_results,
        "wiki_results": wiki_results,
        "provider_results": provider_results,
        "provider_stats": provider_stats,
        "news_api_available": provider_stats["available_count"] > 0 or wiki_available,
        "evidence_found": news_found or wiki_found,
        "evidence_strength": evidence_strength,
        "news_found": news_found,
        "wiki_found": wiki_found,
        "wiki_available": wiki_available,
    }


async def _query_all_providers(client: httpx.AsyncClient, query: str) -> dict:
    """Query all configured providers in parallel and normalize their responses."""
    tasks = {}

    if NEWSDATA_API_KEY:
        tasks["newsdata"] = asyncio.create_task(_check_newsdata(client, query))
    if WORLDNEWS_API_KEY:
        tasks["worldnews"] = asyncio.create_task(_check_worldnews(client, query))
    if NEWSMESH_API_KEY:
        tasks["newsmesh"] = asyncio.create_task(_check_newsmesh(client, query))
    if GNEWS_API_KEY:
        tasks["gnews"] = asyncio.create_task(_check_gnews(client, query))

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))


async def _check_newsdata(client: httpx.AsyncClient, query: str) -> dict:
    try:
        best_result = {"articles": [], "total_results": 0, "found": False, "available": False}
        for variant in _query_variants(query):
            response = await client.get(
                NEWSDATA_URL,
                params={
                    "apikey": NEWSDATA_API_KEY,
                    "q": variant,
                    "language": "en",
                },
            )
            if response.status_code != 200:
                continue

            data = response.json()
            results = data.get("results", [])[:5]
            articles = [
                {
                    "provider": PROVIDER_LABELS["newsdata"],
                    "title": item.get("title", ""),
                    "description": item.get("description", "") or item.get("content", ""),
                    "source": item.get("source_name") or item.get("source_id") or PROVIDER_LABELS["newsdata"],
                    "url": item.get("link", ""),
                    "published_at": item.get("pubDate", ""),
                }
                for item in results
            ]
            total_results = _safe_int(data.get("totalResults"), fallback=len(results))
            candidate = {
                "articles": articles,
                "total_results": total_results,
                "found": bool(articles),
                "available": True,
            }
            best_result = _prefer_provider_result(best_result, candidate)
            if candidate["found"]:
                return candidate

        return best_result
    except Exception as exc:
        print(f"[FactChecker] NewsData.io error: {exc}")
        return {"articles": [], "total_results": 0, "found": False, "available": False}


async def _check_worldnews(client: httpx.AsyncClient, query: str) -> dict:
    try:
        best_result = {"articles": [], "total_results": 0, "found": False, "available": False}
        for variant in _query_variants(query):
            response = await client.get(
                WORLDNEWS_URL,
                params={
                    "text": variant,
                    "language": "en",
                    "number": 5,
                },
                headers={"x-api-key": WORLDNEWS_API_KEY},
            )
            if response.status_code != 200:
                continue

            data = response.json()
            results = data.get("news", [])[:5]
            articles = [
                {
                    "provider": PROVIDER_LABELS["worldnews"],
                    "title": item.get("title", ""),
                    "description": item.get("summary", "") or item.get("text", "")[:300],
                    "source": _source_from_url(item.get("url", "")) or PROVIDER_LABELS["worldnews"],
                    "url": item.get("url", ""),
                    "published_at": item.get("publish_date", ""),
                }
                for item in results
            ]
            total_results = _safe_int(data.get("available"), fallback=len(results))
            candidate = {
                "articles": articles,
                "total_results": total_results,
                "found": bool(articles),
                "available": True,
            }
            best_result = _prefer_provider_result(best_result, candidate)
            if candidate["found"]:
                return candidate

        return best_result
    except Exception as exc:
        print(f"[FactChecker] WorldNewsAPI error: {exc}")
        return {"articles": [], "total_results": 0, "found": False, "available": False}


async def _check_newsmesh(client: httpx.AsyncClient, query: str) -> dict:
    try:
        best_result = {"articles": [], "total_results": 0, "found": False, "available": False}
        for variant in _query_variants(query):
            response = await client.get(
                NEWSMESH_URL,
                params={
                    "apiKey": NEWSMESH_API_KEY,
                    "q": variant,
                    "searchIn": "title,description",
                    "limit": 5,
                    "sortBy": "relevant",
                },
            )
            if response.status_code != 200:
                continue

            data = response.json()
            results = data.get("data", [])[:5]
            articles = [
                {
                    "provider": PROVIDER_LABELS["newsmesh"],
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "source": item.get("source", "") or PROVIDER_LABELS["newsmesh"],
                    "url": item.get("link", ""),
                    "published_at": item.get("published_date", ""),
                }
                for item in results
            ]
            total_results = _safe_int(data.get("total"), fallback=len(results))
            candidate = {
                "articles": articles,
                "total_results": total_results,
                "found": bool(articles),
                "available": True,
            }
            best_result = _prefer_provider_result(best_result, candidate)
            if candidate["found"]:
                return candidate

        return best_result
    except Exception as exc:
        print(f"[FactChecker] NewsMesh error: {exc}")
        return {"articles": [], "total_results": 0, "found": False, "available": False}


async def _check_gnews(client: httpx.AsyncClient, query: str) -> dict:
    try:
        best_result = {"articles": [], "total_results": 0, "found": False, "available": False}
        for variant in _query_variants(query):
            response = await client.get(
                GNEWS_URL,
                params={
                    "apikey": GNEWS_API_KEY,
                    "q": variant,
                    "lang": "en",
                    "max": 5,
                    "sortby": "relevance",
                },
            )
            if response.status_code != 200:
                continue

            data = response.json()
            results = data.get("articles", [])[:5]
            articles = [
                {
                    "provider": PROVIDER_LABELS["gnews"],
                    "title": item.get("title", ""),
                    "description": item.get("description", "") or item.get("content", ""),
                    "source": item.get("source", {}).get("name", "") or PROVIDER_LABELS["gnews"],
                    "url": item.get("url", ""),
                    "published_at": item.get("publishedAt", ""),
                }
                for item in results
            ]
            total_results = _safe_int(data.get("totalArticles"), fallback=len(results))
            candidate = {
                "articles": articles,
                "total_results": total_results,
                "found": bool(articles),
                "available": True,
            }
            best_result = _prefer_provider_result(best_result, candidate)
            if candidate["found"]:
                return candidate

        return best_result
    except Exception as exc:
        print(f"[FactChecker] GNews error: {exc}")
        return {"articles": [], "total_results": 0, "found": False, "available": False}


async def _check_wikipedia(client: httpx.AsyncClient, query: str) -> dict:
    """Search Wikipedia for relevant information."""
    try:
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "utf8": 1,
        }
        response = await client.get(WIKIPEDIA_API_URL, params=search_params)
        if response.status_code != 200:
            return {"results": [], "available": False}

        search_results = response.json().get("query", {}).get("search", [])
        results = []

        for sr in search_results[:3]:
            extract_params = {
                "action": "query",
                "format": "json",
                "titles": sr.get("title", ""),
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exsentences": 3,
            }
            ext_response = await client.get(WIKIPEDIA_API_URL, params=extract_params)
            extract_text = ""
            if ext_response.status_code == 200:
                pages = ext_response.json().get("query", {}).get("pages", {})
                for page_id, page_data in pages.items():
                    if page_id != "-1":
                        extract_text = page_data.get("extract", "")
                        break

            results.append({
                "title": sr.get("title", ""),
                "snippet": _clean_html(sr.get("snippet", "")),
                "extract": extract_text[:500],
                "page_id": sr.get("pageid"),
            })

        return {"results": results, "available": True}
    except Exception as exc:
        print(f"[FactChecker] Wikipedia error: {exc}")
        return {"results": [], "available": False}


def _dedupe_queries(queries: list) -> list:
    """Keep the first generated query per claim."""
    unique_queries = []
    seen_claims = set()
    for query in queries:
        claim_index = query.get("claim_index")
        if claim_index in seen_claims:
            continue
        seen_claims.add(claim_index)
        unique_queries.append(query)
    return unique_queries


def _query_variants(query: str) -> list[str]:
    """Generate a few progressively broader query variants for stricter providers."""
    variants = []
    seen = set()

    def add(value: str):
        cleaned = " ".join(value.split()).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            variants.append(cleaned)

    add(query)

    words = [word for word in query.split() if len(word) > 2]
    if words:
        add(" ".join(words[:5]))
        add(" ".join(words[:3]))

    return variants[:3]


def _prefer_provider_result(current: dict, candidate: dict) -> dict:
    """Keep the provider response with the most usable information."""
    current_articles = len(current.get("articles", []))
    candidate_articles = len(candidate.get("articles", []))
    if candidate_articles > current_articles:
        return candidate
    if candidate_articles == current_articles and candidate.get("total_results", 0) > current.get("total_results", 0):
        return candidate
    return current


def _configured_provider_names() -> list[str]:
    names = []
    if NEWSDATA_API_KEY:
        names.append("newsdata")
    if WORLDNEWS_API_KEY:
        names.append("worldnews")
    if NEWSMESH_API_KEY:
        names.append("newsmesh")
    if GNEWS_API_KEY:
        names.append("gnews")
    return names


def _safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _source_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    return parsed.netloc.replace("www.", "")


def _clean_html(text: str) -> str:
    """Remove HTML tags from Wikipedia snippets."""
    import re
    return re.sub(r"<[^>]+>", "", text)


def _assess_evidence_strength(news_results: list, wiki_results: list, provider_stats: dict) -> str:
    """
    Assess overall evidence strength.
    Returns: 'strong', 'moderate', 'weak', 'none', or 'unavailable'
    """
    provider_hits = provider_stats.get("hit_count", 0)
    wiki_count = sum(len(result.get("results", [])) for result in wiki_results)
    news_hits = sum(result.get("total_results", 0) for result in news_results)

    if provider_stats.get("available_count", 0) == 0 and not any(result.get("available", False) for result in wiki_results):
        return "unavailable"
    if news_hits == 0 and wiki_count == 0:
        return "none"
    if provider_hits >= 2 and wiki_count >= 1:
        return "strong"
    if provider_hits >= 1 or wiki_count >= 1:
        return "moderate"
    return "weak"
