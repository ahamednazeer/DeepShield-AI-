import json
from datetime import datetime, timezone

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from config import LINK_PROVIDER_TIMEOUT_SECONDS, URLSCAN_API_KEY, VIRUSTOTAL_API_KEY
from database import get_db
from models import LinkAnalysisHistoryResponse, LinkAnalysisRequest, LinkAnalysisResponse
from services.audit import log_event
from services.moderation import (
    BLOCKED_VERDICTS,
    REVIEW_VERDICTS,
    apply_moderation_rules,
    create_notification,
    notify_admins,
    resolve_permissions,
    to_moderation_state,
)
from services.verdicts import normalize_verdict
from detectors.link_detector import normalize_url, resolve_link_outcome, summarize_provider_gate

router = APIRouter(prefix="/api/link", tags=["link-analysis"])


def _parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value)
        return default if parsed is None else parsed
    except (json.JSONDecodeError, TypeError):
        return default


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


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


def _build_vt_signals(summary: dict) -> list[dict]:
    stats = summary.get("stats") or {}
    malicious = int(stats.get("malicious", 0) or 0)
    suspicious = int(stats.get("suspicious", 0) or 0)
    risk_score = summary.get("risk_score")
    signals = []
    if malicious:
        signals.append(
            {
                "source": "virustotal",
                "label": f"VirusTotal flagged the URL as malicious with {malicious} positive engines",
                "severity": "high",
                "weight": round(max(0.2, risk_score or 0.0), 3),
                "details": {"stats": stats},
            }
        )
    elif suspicious:
        signals.append(
            {
                "source": "virustotal",
                "label": f"VirusTotal reported suspicious detections from {suspicious} engines",
                "severity": "medium",
                "weight": round(max(0.12, risk_score or 0.0), 3),
                "details": {"stats": stats},
            }
        )
    return signals


def _build_urlscan_signals(summary: dict) -> list[dict]:
    score_value = float(summary.get("score") or 0)
    risk_score = summary.get("risk_score")
    categories = list(summary.get("categories") or [])
    downloads = int(summary.get("downloads") or 0)
    signals = []
    if score_value >= 75:
        signals.append(
            {
                "source": "urlscan",
                "label": f"urlscan assigned a high-risk score of {int(score_value)}",
                "severity": "high",
                "weight": round(max(0.25, risk_score or 0.0), 3),
                "details": {"categories": categories},
            }
        )
    elif score_value >= 20 or categories:
        signals.append(
            {
                "source": "urlscan",
                "label": f"urlscan flagged the page as suspicious ({', '.join(categories) or 'score-only'})",
                "severity": "medium",
                "weight": round(max(0.12, risk_score or 0.0), 3),
                "details": {"categories": categories},
            }
        )
    if downloads:
        signals.append(
            {
                "source": "urlscan",
                "label": "The page triggered file downloads during the scan",
                "severity": "high",
                "weight": 0.16,
                "details": {"download_count": downloads},
            }
        )
    return signals


def _build_system_signals(url_info: dict) -> list[dict]:
    if not (url_info.get("is_private") or url_info.get("is_localhost")):
        return []
    return [
        {
            "source": "system",
            "label": "Private or localhost targets are not sent to external scanners",
            "severity": "high",
            "weight": 0.8,
            "details": {},
        }
    ]


async def _refresh_virustotal_summary(summary: dict) -> tuple[dict, bool]:
    analysis_id = summary.get("analysis_id")
    if not VIRUSTOTAL_API_KEY or not analysis_id:
        return summary, False
    if summary.get("analysis_status") == "completed":
        return summary, False

    headers = {"x-apikey": VIRUSTOTAL_API_KEY, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=LINK_PROVIDER_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(f"https://www.virustotal.com/api/v3/analyses/{analysis_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()

    data = (payload.get("data") or {}) if isinstance(payload, dict) else {}
    attributes = data.get("attributes") or {}
    analysis_status = attributes.get("status") or "pending"
    stats = attributes.get("stats") or {}
    results = attributes.get("results") or {}
    malicious = int(stats.get("malicious", 0) or 0)
    suspicious = int(stats.get("suspicious", 0) or 0)
    harmless = int(stats.get("harmless", 0) or 0)
    undetected = int(stats.get("undetected", 0) or 0)
    total = malicious + suspicious + harmless + undetected
    risk_score = None
    if analysis_status == "completed" and total:
        risk_score = round(_clamp((malicious + (0.6 * suspicious)) / total), 4)

    detections = []
    if analysis_status == "completed":
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

    refreshed = {
        "status": "completed" if analysis_status == "completed" else "pending",
        "analysis_id": data.get("id") or analysis_id,
        "analysis_status": analysis_status,
        "stats": stats,
        "detections": detections,
        "risk_score": risk_score,
    }
    return refreshed, refreshed != summary


async def _refresh_urlscan_summary(summary: dict) -> tuple[dict, dict, list[str], str | None, bool]:
    uuid = summary.get("uuid")
    if not URLSCAN_API_KEY or not uuid:
        return summary, {}, [], None, False
    if summary.get("status") == "completed":
        page = summary.get("page") or {}
        return summary, page, [page.get("url")] if page.get("url") else [], page.get("url"), False

    headers = {"API-Key": URLSCAN_API_KEY}
    async with httpx.AsyncClient(timeout=LINK_PROVIDER_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(f"https://urlscan.io/api/v1/result/{uuid}/", headers=headers)
        if response.status_code == 404:
            return summary, {}, [], None, False
        response.raise_for_status()
        payload = response.json()

    verdicts = payload.get("verdicts") or {}
    urlscan_verdict = verdicts.get("urlscan") or {}
    score_value = float(urlscan_verdict.get("score") or 0)
    risk_score = round(_clamp(max(score_value, 0.0) / 100.0), 4)
    categories = list(urlscan_verdict.get("categories") or [])
    brands = list(urlscan_verdict.get("brands") or [])
    page = payload.get("page") or {}
    meta = payload.get("meta") or {}
    downloads = (((meta.get("processors") or {}).get("download") or {}).get("data")) or []
    lists = payload.get("lists") or {}
    redirect_chain = []
    for candidate in [payload.get("task", {}).get("url"), page.get("url"), *(lists.get("urls") or [])]:
        if candidate and candidate not in redirect_chain:
            redirect_chain.append(candidate)
        if len(redirect_chain) >= 6:
            break

    refreshed = {
        "status": "completed",
        "uuid": uuid,
        "visibility": summary.get("visibility"),
        "scan_result": summary.get("scan_result"),
        "message": summary.get("message"),
        "risk_score": risk_score,
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
    }
    page_metadata = {
        "title": page.get("title"),
        "status": page.get("status"),
        "domain": page.get("domain"),
        "server": page.get("server"),
        "country": page.get("country"),
        "ip": page.get("ip"),
        "redirected": page.get("redirected"),
    }
    return refreshed, page_metadata, redirect_chain, page.get("url"), True


async def _refresh_pending_providers(db: aiosqlite.Connection, row: dict) -> dict:
    provider_summary = _parse_json(row.get("provider_summary"), {})
    vt_summary = provider_summary.get("virustotal") or {}
    urlscan_summary = provider_summary.get("urlscan") or {}
    page_metadata = _parse_json(row.get("page_metadata"), {})
    redirect_chain = _parse_json(row.get("redirect_chain"), [])
    updated = False

    try:
        refreshed_vt, vt_changed = await _refresh_virustotal_summary(vt_summary)
        provider_summary["virustotal"] = refreshed_vt
        updated = updated or vt_changed
    except httpx.HTTPError:
        pass

    try:
        refreshed_urlscan, refreshed_page_metadata, refreshed_redirects, refreshed_final_url, urlscan_changed = await _refresh_urlscan_summary(urlscan_summary)
        provider_summary["urlscan"] = refreshed_urlscan
        if refreshed_page_metadata:
            page_metadata = {
                **page_metadata,
                **{key: value for key, value in refreshed_page_metadata.items() if value is not None},
            }
        if refreshed_redirects:
            redirect_chain = [item for item in refreshed_redirects if item]
        if refreshed_final_url:
            row["final_url"] = refreshed_final_url
        updated = updated or urlscan_changed
    except httpx.HTTPError:
        pass

    if not updated:
        return row

    url_info = normalize_url(row.get("normalized_url") or row.get("input_url") or "")
    skip_external = bool(url_info.get("is_private") or url_info.get("is_localhost"))
    signals = sorted(
        [
            *_build_system_signals(url_info),
            *_build_vt_signals(provider_summary.get("virustotal", {})),
            *_build_urlscan_signals(provider_summary.get("urlscan", {})),
        ],
        key=lambda item: (item.get("weight", 0.0), item.get("severity", "")),
        reverse=True,
    )
    resolved = resolve_link_outcome(
        provider_summary,
        skip_external=skip_external,
        signals=signals,
    )

    await db.execute(
        """UPDATE link_analyses SET
           status = ?,
           final_url = ?,
           domain = ?,
           risk_score = ?,
           verdict = ?,
           raw_verdict = ?,
           signals = ?,
           provider_summary = ?,
           redirect_chain = ?,
           page_metadata = ?,
           completed_at = ?
           WHERE id = ?""",
        (
            resolved["status"],
            row.get("final_url") or row.get("normalized_url"),
            page_metadata.get("domain") or row.get("domain") or url_info["hostname"],
            resolved["risk_score"],
            resolved["verdict"],
            resolved["raw_verdict"],
            json.dumps(resolved["signals"]),
            json.dumps(provider_summary),
            json.dumps(redirect_chain),
            json.dumps(page_metadata),
            datetime.now(timezone.utc).isoformat() if resolved["status"] == "completed" else row.get("completed_at"),
            row["id"],
        ),
    )
    if resolved["status"] == "completed":
        await apply_moderation_rules(
            db,
            "link",
            row["id"],
            row["user_id"],
            resolved["verdict"],
            resolved["risk_score"],
        )
    await db.commit()
    refreshed = await _fetch_link_analysis(db, row["id"], {"id": row["user_id"], "role": "admin"})
    return refreshed or row
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


async def _fetch_link_analysis(
    db: aiosqlite.Connection,
    analysis_id: int,
    current_user: dict,
) -> dict | None:
    if current_user["role"] == "admin":
        cursor = await db.execute("SELECT * FROM link_analyses WHERE id = ?", (analysis_id,))
    else:
        cursor = await db.execute(
            "SELECT * FROM link_analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"]),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def _row_to_response(
    db: aiosqlite.Connection,
    row: dict,
    current_user: dict,
) -> LinkAnalysisResponse:
    cursor = await db.execute(
        "SELECT * FROM content_moderation WHERE content_type = 'link' AND content_id = ?",
        (row["id"],),
    )
    moderation_row = await cursor.fetchone()
    moderation = dict(moderation_row) if moderation_row else None

    return LinkAnalysisResponse(
        id=row["id"],
        user_id=row["user_id"],
        input_url=row["input_url"],
        normalized_url=row.get("normalized_url"),
        final_url=row.get("final_url"),
        domain=row.get("domain"),
        status=row["status"],
        risk_score=row.get("risk_score"),
        verdict=row.get("verdict"),
        raw_verdict=row.get("raw_verdict"),
        effective_verdict=normalize_verdict(
            moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else row.get("verdict")
        ),
        signals=_parse_json(row.get("signals"), []),
        provider_summary=_parse_json(row.get("provider_summary"), {}),
        redirect_chain=_parse_json(row.get("redirect_chain"), []),
        page_metadata=_parse_json(row.get("page_metadata"), {}),
        processing_time=row.get("processing_time"),
        created_at=str(row["created_at"]),
        completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        permissions=resolve_permissions(current_user, row.get("verdict"), moderation, row.get("status")),
        moderation=to_moderation_state(moderation),
    )


@router.post("/analyze", response_model=LinkAnalysisResponse)
async def analyze_url(
    request: LinkAnalysisRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    if len(request.url.strip()) > 2048:
        raise HTTPException(status_code=400, detail="URL is too long")

    cursor = await db.execute(
        """INSERT INTO link_analyses (user_id, input_url, status)
           VALUES (?, ?, 'processing')""",
        (current_user["id"], request.url.strip()),
    )
    analysis_id = cursor.lastrowid
    await log_event(
        db,
        action="link_analysis_requested",
        target_type="link",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
        details={"input_url": request.url.strip()},
    )
    await db.commit()

    try:
        from detectors.link_detector import analyze_link as run_pipeline

        result = await run_pipeline(request.url.strip())
        verdict = normalize_verdict(result.get("verdict")) or "UNKNOWN"
        raw_verdict = result.get("raw_verdict") or verdict
        risk_score = result.get("risk_score")
        analysis_status = result.get("status") or "completed"
        completed_at = datetime.now(timezone.utc).isoformat() if analysis_status == "completed" else None

        await db.execute(
            """UPDATE link_analyses SET
               status = ?,
               normalized_url = ?,
               final_url = ?,
               domain = ?,
               risk_score = ?,
               verdict = ?,
               raw_verdict = ?,
               signals = ?,
               provider_summary = ?,
               redirect_chain = ?,
               page_metadata = ?,
               processing_time = ?,
               completed_at = ?
               WHERE id = ?""",
            (
                analysis_status,
                result.get("normalized_url"),
                result.get("final_url"),
                result.get("domain"),
                risk_score,
                verdict,
                raw_verdict,
                json.dumps(result.get("signals", [])),
                json.dumps(result.get("provider_summary", {})),
                json.dumps(result.get("redirect_chain", [])),
                json.dumps(result.get("page_metadata", {})),
                result.get("processing_time"),
                completed_at,
                analysis_id,
            ),
        )

        if analysis_status == "completed":
            moderation = await apply_moderation_rules(
                db,
                "link",
                analysis_id,
                current_user["id"],
                verdict,
                risk_score,
            )
            effective_verdict = moderation.get("manual_verdict") if moderation.get("manual_verdict") else verdict
            common_effective_verdict = normalize_verdict(effective_verdict)

            await create_notification(
                db,
                user_id=current_user["id"],
                title="Link analysis completed",
                message=f"URL scan finished with verdict {common_effective_verdict or 'UNKNOWN'}.",
                severity="info",
                kind="analysis",
                target_type="link",
                target_id=analysis_id,
            )
            if common_effective_verdict in REVIEW_VERDICTS or moderation.get("is_flagged"):
                severity = "critical" if common_effective_verdict in BLOCKED_VERDICTS else "warning"
                await notify_admins(
                    db,
                    title="High-risk link requires review",
                    message=f"Link analysis #{analysis_id} was marked {common_effective_verdict or 'UNKNOWN'} and queued for review.",
                    severity=severity,
                    kind="moderation",
                    target_type="link",
                    target_id=analysis_id,
                )

            await log_event(
                db,
                action="link_analysis_completed",
                target_type="link",
                target_id=analysis_id,
                actor_user_id=current_user["id"],
                details={
                    "verdict": verdict,
                    "raw_verdict": raw_verdict,
                    "effective_verdict": common_effective_verdict,
                    "score": risk_score,
                    "final_url": result.get("final_url"),
                },
            )
        else:
            await log_event(
                db,
                action="link_analysis_pending_providers",
                target_type="link",
                target_id=analysis_id,
                actor_user_id=current_user["id"],
                details={
                    "status": analysis_status,
                    "provider_summary": result.get("provider_summary", {}),
                },
            )
        await db.commit()

        row = await _fetch_link_analysis(db, analysis_id, current_user)
        return await _row_to_response(db, row, current_user)

    except ValueError as exc:
        await db.execute("UPDATE link_analyses SET status = 'failed' WHERE id = ?", (analysis_id,))
        await log_event(
            db,
            action="link_analysis_failed",
            target_type="link",
            target_id=analysis_id,
            actor_user_id=current_user["id"],
            details={"error": str(exc)},
        )
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        await db.execute("UPDATE link_analyses SET status = 'failed' WHERE id = ?", (analysis_id,))
        await log_event(
            db,
            action="link_analysis_failed",
            target_type="link",
            target_id=analysis_id,
            actor_user_id=current_user["id"],
            details={"error": str(exc)},
        )
        await create_notification(
            db,
            user_id=current_user["id"],
            title="Link analysis failed",
            message="The submitted URL could not be analyzed.",
            severity="critical",
            kind="analysis",
            target_type="link",
            target_id=analysis_id,
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(exc)}")


@router.get("/analysis/{analysis_id}", response_model=LinkAnalysisResponse)
async def get_link_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await _fetch_link_analysis(db, analysis_id, current_user)
    if not row:
        raise HTTPException(status_code=404, detail="Link analysis not found")
    provider_summary = _parse_json(row.get("provider_summary"), {})
    gate = summarize_provider_gate(
        provider_summary,
        skip_external=False,
    )
    if row.get("status") == "processing" or gate["pending"]:
        row = await _refresh_pending_providers(db, row)
    return await _row_to_response(db, row, current_user)


@router.get("/history", response_model=LinkAnalysisHistoryResponse)
async def get_link_history(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT * FROM link_analyses WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    )
    rows = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute("SELECT COUNT(*) FROM link_analyses WHERE user_id = ?", (current_user["id"],))
    total = (await cursor.fetchone())[0]
    analyses = [await _row_to_response(db, row, current_user) for row in rows]
    return LinkAnalysisHistoryResponse(analyses=analyses, total=total)
