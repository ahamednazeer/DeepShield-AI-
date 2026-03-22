import asyncio
import json
import time
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from auth import get_current_user, require_active_user
from database import get_db
from models import (
    AnalysisHistoryResponse,
    AnalysisResponse,
    AnalysisStartRequest,
    DashboardStats,
    MediaModelCatalogResponse,
    MediaModelOption,
)
from services.audit import log_event
from services.model_catalog import list_media_models, resolve_media_model_runtime, resolve_selected_model
from services.content import build_unified_history
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

router = APIRouter(prefix="/api", tags=["analysis"])
ANALYSIS_PROGRESS = {}


async def _fetch_analysis(
    db: aiosqlite.Connection,
    analysis_id: int,
    current_user: dict,
) -> dict | None:
    if current_user["role"] == "admin":
        cursor = await db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    else:
        cursor = await db.execute(
            "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"]),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def _build_analysis_response(
    db: aiosqlite.Connection,
    analysis: dict,
    current_user: dict,
) -> AnalysisResponse:
    cursor = await db.execute(
        "SELECT * FROM evidence_items WHERE analysis_id = ?",
        (analysis["id"],),
    )
    evidence = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute(
        "SELECT * FROM content_moderation WHERE content_type = 'media' AND content_id = ?",
        (analysis["id"],),
    )
    moderation_row = await cursor.fetchone()
    moderation = dict(moderation_row) if moderation_row else None

    progress = ANALYSIS_PROGRESS.get(analysis["id"]) if analysis["status"] == "processing" else None
    frames_total = progress.get("frames_total") if progress else None
    frames_processed = progress.get("frames_processed") if progress else None
    progress_percent = None
    if frames_total:
        progress_percent = round((frames_processed or 0) / frames_total * 100, 1)

    return AnalysisResponse(
        id=analysis["id"],
        user_id=analysis["user_id"],
        filename=analysis["filename"],
        original_filename=analysis["original_filename"],
        media_type=analysis["media_type"],
        file_size=analysis["file_size"],
        status=analysis["status"],
        overall_score=analysis["overall_score"],
        verdict=analysis["verdict"],
        raw_verdict=analysis.get("raw_verdict"),
        effective_verdict=normalize_verdict(
            moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else analysis["verdict"]
        ),
        image_score=analysis["image_score"],
        video_score=analysis["video_score"],
        audio_score=analysis["audio_score"],
        processing_time=analysis["processing_time"],
        selected_model=analysis.get("selected_model"),
        model_version=analysis["model_version"],
        frames_total=frames_total,
        frames_processed=frames_processed,
        progress_percent=progress_percent,
        created_at=str(analysis["created_at"]),
        completed_at=str(analysis["completed_at"]) if analysis["completed_at"] else None,
        evidence=evidence,
        permissions=resolve_permissions(current_user, analysis["verdict"], moderation, analysis.get("status")),
        moderation=to_moderation_state(moderation),
    )


async def run_analysis(analysis_id: int):
    """Run the full analysis pipeline in background."""
    from config import DATABASE_PATH, EVIDENCE_DIR, UPLOAD_DIR

    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
        analysis_row = await cursor.fetchone()
        if not analysis_row:
            return

        analysis = dict(analysis_row)
        await db.execute(
            "UPDATE analyses SET status = 'processing' WHERE id = ?",
            (analysis_id,),
        )
        await log_event(
            db,
            action="analysis_processing_started",
            target_type="media",
            target_id=analysis_id,
            actor_user_id=analysis["user_id"],
        )
        await db.commit()

        start_time = time.time()
        file_path = str(UPLOAD_DIR / analysis["filename"])
        media_type = analysis["media_type"]
        model_runtime = resolve_media_model_runtime(media_type, analysis.get("selected_model"))

        try:
            result = {}
            evidence_items = []

            if media_type == "image":
                from detectors.image_detector import detect_image

                result = await asyncio.to_thread(detect_image, file_path, model_runtime)
                if "heatmap" in result:
                    heatmap_name = f"heatmap_{analysis_id}.png"
                    heatmap_path = EVIDENCE_DIR / heatmap_name
                    result["heatmap"].save(str(heatmap_path))
                    evidence_items.append(
                        {
                            "evidence_type": "heatmap",
                            "title": "Forensic Heatmap",
                            "description": "Overlay heatmap of compression anomalies. Yellow and red regions indicate stronger forensic inconsistency.",
                            "severity": "info",
                            "file_path": heatmap_name,
                        }
                    )
                    del result["heatmap"]

            elif media_type == "video":
                from detectors.video_detector import detect_video

                ANALYSIS_PROGRESS[analysis_id] = {
                    "frames_processed": 0,
                    "frames_total": None,
                    "updated_at": time.time(),
                }

                def on_progress(processed, total):
                    ANALYSIS_PROGRESS[analysis_id] = {
                        "frames_processed": processed,
                        "frames_total": total,
                        "updated_at": time.time(),
                    }

                result = await asyncio.to_thread(detect_video, file_path, on_progress=on_progress, model_config=model_runtime)

            elif media_type == "audio":
                from detectors.audio_detector import detect_audio

                result = await asyncio.to_thread(detect_audio, file_path)

            processing_time = round(time.time() - start_time, 2)

            for item in result.get("evidence", []):
                evidence_items.append(
                    {
                        "evidence_type": item.get("type", "artifact"),
                        "title": item.get("title", "Unknown"),
                        "description": item.get("description", ""),
                        "severity": item.get("severity", "info"),
                        "data": json.dumps(item) if item else None,
                    }
                )

            for item in evidence_items:
                await db.execute(
                    """INSERT INTO evidence_items
                       (analysis_id, evidence_type, title, description, severity, data, file_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        analysis_id,
                        item["evidence_type"],
                        item["title"],
                        item.get("description"),
                        item.get("severity", "info"),
                        item.get("data"),
                        item.get("file_path"),
                    ),
                )

            image_score = result.get("overall_score") if media_type == "image" else None
            video_score = result.get("overall_score") if media_type == "video" else None
            audio_score = result.get("overall_score") if media_type == "audio" else None
            raw_verdict = result.get("verdict", "UNKNOWN")
            common_verdict = normalize_verdict(raw_verdict) or "UNKNOWN"

            await db.execute(
                """UPDATE analyses SET
                   status = 'completed',
                   overall_score = ?,
                   verdict = ?,
                   raw_verdict = ?,
                   image_score = ?,
                   video_score = ?,
                   audio_score = ?,
                   processing_time = ?,
                   model_version = ?,
                   completed_at = ?
                   WHERE id = ?""",
                (
                    result.get("overall_score", 0),
                    common_verdict,
                    raw_verdict,
                    image_score,
                    video_score,
                    audio_score,
                    processing_time,
                    result.get("model_version", analysis.get("model_version", "1.0.0")),
                    datetime.now(timezone.utc).isoformat(),
                    analysis_id,
                ),
            )

            moderation = await apply_moderation_rules(
                db,
                "media",
                analysis_id,
                analysis["user_id"],
                common_verdict,
                result.get("overall_score"),
            )

            effective_verdict = moderation.get("manual_verdict") if moderation.get("manual_verdict") else common_verdict
            common_effective_verdict = normalize_verdict(effective_verdict)
            await create_notification(
                db,
                user_id=analysis["user_id"],
                title="Media analysis completed",
                message=f"{analysis['original_filename']} finished with verdict {common_effective_verdict or 'UNKNOWN'}.",
                severity="info",
                kind="analysis",
                target_type="media",
                target_id=analysis_id,
            )

            if common_effective_verdict in REVIEW_VERDICTS or moderation.get("is_flagged"):
                severity = "critical" if common_effective_verdict in BLOCKED_VERDICTS else "warning"
                await notify_admins(
                    db,
                    title="High-risk media requires review",
                    message=f"{analysis['original_filename']} was marked {common_effective_verdict or 'UNKNOWN'} and added to the review queue.",
                    severity=severity,
                    kind="moderation",
                    target_type="media",
                    target_id=analysis_id,
                )

            await log_event(
                db,
                action="analysis_completed",
                target_type="media",
                target_id=analysis_id,
                actor_user_id=analysis["user_id"],
                details={
                    "verdict": result.get("verdict"),
                    "raw_verdict": raw_verdict,
                    "effective_verdict": common_effective_verdict,
                    "score": result.get("overall_score"),
                },
            )
            await db.commit()
            ANALYSIS_PROGRESS.pop(analysis_id, None)

        except Exception as exc:
            await db.execute(
                "UPDATE analyses SET status = 'failed' WHERE id = ?",
                (analysis_id,),
            )
            await log_event(
                db,
                action="analysis_failed",
                target_type="media",
                target_id=analysis_id,
                actor_user_id=analysis["user_id"],
                details={"error": str(exc)},
            )
            await create_notification(
                db,
                user_id=analysis["user_id"],
                title="Media analysis failed",
                message=f"{analysis['original_filename']} could not be analyzed.",
                severity="critical",
                kind="analysis",
                target_type="media",
                target_id=analysis_id,
            )
            await db.commit()
            ANALYSIS_PROGRESS.pop(analysis_id, None)
            print(f"Analysis {analysis_id} failed: {exc}")
            import traceback

            traceback.print_exc()


@router.post("/analysis/start/{analysis_id}")
async def start_analysis(
    analysis_id: int,
    background_tasks: BackgroundTasks,
    payload: AnalysisStartRequest | None = None,
    current_user: dict = Depends(require_active_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    analysis = await _fetch_analysis(db, analysis_id, current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis["status"] not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"Analysis is already {analysis['status']}")

    selected_model = payload.selected_model if payload else analysis.get("selected_model")
    try:
        selected_model = resolve_selected_model(analysis["media_type"], selected_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.execute(
        "UPDATE analyses SET selected_model = ? WHERE id = ?",
        (selected_model, analysis_id),
    )
    background_tasks.add_task(run_analysis, analysis_id)
    await log_event(
        db,
        action="analysis_requested",
        target_type="media",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
        details={"selected_model": selected_model},
    )
    await db.commit()
    return {"message": "Analysis started", "id": analysis_id, "status": "processing", "selected_model": selected_model}


@router.get("/models/{media_type}", response_model=MediaModelCatalogResponse)
async def get_media_models(
    media_type: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        options = list_media_models(media_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MediaModelCatalogResponse(
        media_type=media_type,
        models=[MediaModelOption(**option) for option in options],
    )


@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    analysis = await _fetch_analysis(db, analysis_id, current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return await _build_analysis_response(db, analysis, current_user)


@router.get("/analysis/history/list", response_model=AnalysisHistoryResponse)
async def get_history(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    )
    rows = await cursor.fetchall()

    cursor2 = await db.execute(
        "SELECT COUNT(*) as cnt FROM analyses WHERE user_id = ?",
        (current_user["id"],),
    )
    total_row = await cursor2.fetchone()

    analyses = [await _build_analysis_response(db, dict(row), current_user) for row in rows]
    return AnalysisHistoryResponse(analyses=analyses, total=dict(total_row)["cnt"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    uid = current_user["id"]

    cursor = await db.execute("SELECT COUNT(*) FROM analyses WHERE user_id = ?", (uid,))
    media_total = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM text_analyses WHERE user_id = ?", (uid,))
    text_total = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM link_analyses WHERE user_id = ?", (uid,))
    link_total = (await cursor.fetchone())[0]

    cursor = await db.execute(
        "SELECT COUNT(*) FROM analyses WHERE user_id = ? AND verdict = 'MANIPULATED'",
        (uid,),
    )
    media_manipulated = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM text_analyses WHERE user_id = ? AND verdict = 'MANIPULATED'",
        (uid,),
    )
    text_risky = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM link_analyses WHERE user_id = ? AND verdict = 'MANIPULATED'",
        (uid,),
    )
    link_risky = (await cursor.fetchone())[0]
    deepfake_count = media_manipulated + text_risky + link_risky

    cursor = await db.execute(
        "SELECT COUNT(*) FROM analyses WHERE user_id = ? AND verdict = 'AUTHENTIC'",
        (uid,),
    )
    media_authentic = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM text_analyses WHERE user_id = ? AND verdict = 'AUTHENTIC'",
        (uid,),
    )
    text_authentic = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM link_analyses WHERE user_id = ? AND verdict = 'AUTHENTIC'",
        (uid,),
    )
    link_authentic = (await cursor.fetchone())[0]
    authentic_count = media_authentic + text_authentic + link_authentic

    cursor = await db.execute(
        "SELECT COUNT(*) FROM analyses WHERE user_id = ? AND verdict = 'SUSPICIOUS'",
        (uid,),
    )
    media_suspicious = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM text_analyses WHERE user_id = ? AND verdict = 'SUSPICIOUS'",
        (uid,),
    )
    text_suspicious = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM link_analyses WHERE user_id = ? AND verdict = 'SUSPICIOUS'",
        (uid,),
    )
    link_suspicious = (await cursor.fetchone())[0]
    suspicious_count = media_suspicious + text_suspicious + link_suspicious

    cursor = await db.execute(
        """SELECT AVG(score_value) FROM (
               SELECT overall_score AS score_value FROM analyses WHERE user_id = ? AND status = 'completed'
               UNION ALL
               SELECT final_score AS score_value FROM text_analyses WHERE user_id = ? AND status = 'completed'
               UNION ALL
               SELECT risk_score AS score_value FROM link_analyses WHERE user_id = ? AND status = 'completed'
           )""",
        (uid, uid, uid),
    )
    avg_row = await cursor.fetchone()
    avg_confidence = round((avg_row[0] or 0) * 100, 1)

    cursor = await db.execute(
        "SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
        (uid,),
    )
    recent_media_rows = [dict(row) for row in await cursor.fetchall()]
    recent_analyses = [await _build_analysis_response(db, row, current_user) for row in recent_media_rows]

    cursor = await db.execute(
        "SELECT media_type, COUNT(*) as cnt FROM analyses WHERE user_id = ? GROUP BY media_type",
        (uid,),
    )
    media_dist = {dict(row)["media_type"]: dict(row)["cnt"] for row in await cursor.fetchall()}

    verdict_dist: dict[str, int] = {}
    cursor = await db.execute(
        "SELECT verdict, COUNT(*) as cnt FROM analyses WHERE user_id = ? AND verdict IS NOT NULL GROUP BY verdict",
        (uid,),
    )
    for row in await cursor.fetchall():
        payload = dict(row)
        verdict_key = normalize_verdict(payload["verdict"]) or "UNKNOWN"
        verdict_dist[verdict_key] = verdict_dist.get(verdict_key, 0) + payload["cnt"]
    cursor = await db.execute(
        "SELECT verdict, COUNT(*) as cnt FROM link_analyses WHERE user_id = ? AND verdict IS NOT NULL GROUP BY verdict",
        (uid,),
    )
    for row in await cursor.fetchall():
        payload = dict(row)
        verdict_key = normalize_verdict(payload["verdict"]) or "UNKNOWN"
        verdict_dist[verdict_key] = verdict_dist.get(verdict_key, 0) + payload["cnt"]
    cursor = await db.execute(
        "SELECT verdict, COUNT(*) as cnt FROM text_analyses WHERE user_id = ? AND verdict IS NOT NULL GROUP BY verdict",
        (uid,),
    )
    for row in await cursor.fetchall():
        payload = dict(row)
        verdict_key = normalize_verdict(payload["verdict"]) or "UNKNOWN"
        verdict_dist[verdict_key] = verdict_dist.get(verdict_key, 0) + payload["cnt"]

    cursor = await db.execute(
        "SELECT COUNT(*) FROM content_moderation WHERE owner_user_id = ? AND is_flagged = 1",
        (uid,),
    )
    flagged_count = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM content_moderation WHERE owner_user_id = ? AND review_status = 'pending_review'",
        (uid,),
    )
    pending_review = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (uid,),
    )
    unread_notifications = (await cursor.fetchone())[0]

    recent_items = await build_unified_history(db, current_user, include_all=False, limit=8)

    return DashboardStats(
        total_analyses=media_total + text_total + link_total,
        deepfake_count=deepfake_count,
        authentic_count=authentic_count,
        suspicious_count=suspicious_count,
        avg_confidence=avg_confidence,
        recent_analyses=recent_analyses,
        media_type_distribution=media_dist,
        verdict_distribution=verdict_dist,
        total_media_analyses=media_total,
        total_text_analyses=text_total,
        total_link_analyses=link_total,
        total_content=media_total + text_total + link_total,
        flagged_content=flagged_count,
        pending_review=pending_review,
        unread_notifications=unread_notifications,
        content_type_distribution={"media": media_total, "text": text_total, "link": link_total},
        recent_items=recent_items,
    )
