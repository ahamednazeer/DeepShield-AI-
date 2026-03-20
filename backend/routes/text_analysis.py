"""Text and fake news analysis routes."""

import json
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_db
from models import TextAnalysisHistoryResponse, TextAnalysisRequest, TextAnalysisResponse
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

router = APIRouter(prefix="/api/text", tags=["text-analysis"])


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


async def _fetch_text_analysis(
    db: aiosqlite.Connection,
    analysis_id: int,
    current_user: dict,
) -> dict | None:
    if current_user["role"] == "admin":
        cursor = await db.execute("SELECT * FROM text_analyses WHERE id = ?", (analysis_id,))
    else:
        cursor = await db.execute(
            "SELECT * FROM text_analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"]),
        )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def _row_to_response(
    db: aiosqlite.Connection,
    row: dict,
    current_user: dict,
) -> TextAnalysisResponse:
    claims = _parse_json(row.get("claims"), [])
    evidence = _parse_json(row.get("evidence"), [])
    explanation = _parse_json(row.get("explanation"), {})
    semantic_results = _parse_json(row.get("semantic_results"), [])

    cursor = await db.execute(
        "SELECT * FROM content_moderation WHERE content_type = 'text' AND content_id = ?",
        (row["id"],),
    )
    moderation_row = await cursor.fetchone()
    moderation = dict(moderation_row) if moderation_row else None

    claim_context = explanation.get("claim_context") if isinstance(explanation, dict) else None
    llm_fact_check = explanation.get("llm_fact_check") if isinstance(explanation, dict) else None
    return TextAnalysisResponse(
        id=row["id"],
        user_id=row["user_id"],
        input_text=row["input_text"],
        source_url=row.get("source_url"),
        status=row["status"],
        nlp_score=row.get("nlp_score"),
        fact_score=row.get("fact_score"),
        credibility_score=row.get("credibility_score"),
        final_score=row.get("final_score"),
        verdict=row.get("verdict"),
        raw_verdict=row.get("raw_verdict"),
        effective_verdict=normalize_verdict(
            moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else row.get("verdict")
        ),
        verdict_label=row.get("verdict_label"),
        claims=claims if isinstance(claims, list) else [],
        evidence=evidence if isinstance(evidence, list) else [],
        explanation=explanation if isinstance(explanation, dict) else {},
        semantic_results=semantic_results if isinstance(semantic_results, list) else [],
        claim_context=claim_context if isinstance(claim_context, dict) else None,
        llm_fact_check=llm_fact_check if isinstance(llm_fact_check, dict) else None,
        processing_time=row.get("processing_time"),
        created_at=str(row["created_at"]),
        completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        permissions=resolve_permissions(current_user, row.get("verdict"), moderation, row.get("status")),
        moderation=to_moderation_state(moderation),
    )


@router.post("/analyze", response_model=TextAnalysisResponse)
async def analyze_text(
    request: TextAnalysisRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(request.text) > 10000:
        raise HTTPException(status_code=400, detail="Text must be under 10,000 characters")

    cursor = await db.execute(
        """INSERT INTO text_analyses (user_id, input_text, source_url, status)
           VALUES (?, ?, ?, 'processing')""",
        (current_user["id"], request.text.strip(), request.source_url),
    )
    analysis_id = cursor.lastrowid
    await log_event(
        db,
        action="text_analysis_requested",
        target_type="text",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
    )
    await db.commit()

    try:
        from detectors.text_detector import analyze_text as run_pipeline

        result = await run_pipeline(request.text.strip(), request.source_url)
        nlp_score = result.get("classification", {}).get("fake_probability")
        fact_score_val = result.get("fact_score")
        credibility_score = result.get("credibility", {}).get("score")
        final_score = result.get("final_score", 0)
        raw_verdict = result.get("verdict", "UNKNOWN")
        verdict = normalize_verdict(raw_verdict) or "UNKNOWN"
        verdict_label = result.get("verdict_label", "Unknown")

        claims_json = json.dumps(result.get("claims", []))
        evidence_json = json.dumps(result.get("explanation", {}).get("evidence_summary", []))
        explanation_json = json.dumps(result.get("explanation", {}))
        semantic_json = json.dumps(result.get("semantic_results", []))
        processing_time = result.get("processing_time", 0)
        llm_fact_check = result.get("llm_fact_check") or result.get("explanation", {}).get("llm_fact_check")
        claim_context = result.get("claim_context") or result.get("explanation", {}).get("claim_context")

        await db.execute(
            """UPDATE text_analyses SET
               status = 'completed',
               nlp_score = ?,
               fact_score = ?,
               credibility_score = ?,
               final_score = ?,
               verdict = ?,
               raw_verdict = ?,
               verdict_label = ?,
               claims = ?,
               evidence = ?,
               explanation = ?,
               semantic_results = ?,
               processing_time = ?,
               completed_at = ?
               WHERE id = ?""",
            (
                nlp_score,
                fact_score_val,
                credibility_score,
                final_score,
                verdict,
                raw_verdict,
                verdict_label,
                claims_json,
                evidence_json,
                explanation_json,
                semantic_json,
                processing_time,
                datetime.now(timezone.utc).isoformat(),
                analysis_id,
            ),
        )

        moderation = await apply_moderation_rules(
            db,
            "text",
            analysis_id,
            current_user["id"],
            verdict,
            final_score,
        )
        effective_verdict = moderation.get("manual_verdict") if moderation.get("manual_verdict") else verdict
        common_effective_verdict = normalize_verdict(effective_verdict)

        await create_notification(
            db,
            user_id=current_user["id"],
            title="Text analysis completed",
            message=f"Text analysis finished with verdict {common_effective_verdict or 'UNKNOWN'}.",
            severity="info",
            kind="analysis",
            target_type="text",
            target_id=analysis_id,
        )
        if common_effective_verdict in REVIEW_VERDICTS or moderation.get("is_flagged"):
            severity = "critical" if common_effective_verdict in BLOCKED_VERDICTS else "warning"
            await notify_admins(
                db,
                title="High-risk text requires review",
                message=f"Text analysis #{analysis_id} was marked {common_effective_verdict or 'UNKNOWN'} and queued for review.",
                severity=severity,
                kind="moderation",
                target_type="text",
                target_id=analysis_id,
            )

        await log_event(
            db,
            action="text_analysis_completed",
            target_type="text",
            target_id=analysis_id,
            actor_user_id=current_user["id"],
            details={"verdict": verdict, "raw_verdict": raw_verdict, "effective_verdict": common_effective_verdict, "score": final_score},
        )
        await db.commit()

        row = await _fetch_text_analysis(db, analysis_id, current_user)
        return await _row_to_response(db, row, current_user)

    except Exception as exc:
        await db.execute(
            "UPDATE text_analyses SET status = 'failed' WHERE id = ?",
            (analysis_id,),
        )
        await log_event(
            db,
            action="text_analysis_failed",
            target_type="text",
            target_id=analysis_id,
            actor_user_id=current_user["id"],
            details={"error": str(exc)},
        )
        await create_notification(
            db,
            user_id=current_user["id"],
            title="Text analysis failed",
            message="The submitted text could not be analyzed.",
            severity="critical",
            kind="analysis",
            target_type="text",
            target_id=analysis_id,
        )
        await db.commit()
        print(f"[TextAnalysis] Error: {exc}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(exc)}")


@router.get("/analysis/{analysis_id}", response_model=TextAnalysisResponse)
async def get_text_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await _fetch_text_analysis(db, analysis_id, current_user)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return await _row_to_response(db, row, current_user)


@router.get("/history", response_model=TextAnalysisHistoryResponse)
async def get_text_history(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT * FROM text_analyses WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    )
    rows = await cursor.fetchall()

    cursor2 = await db.execute(
        "SELECT COUNT(*) as cnt FROM text_analyses WHERE user_id = ?",
        (current_user["id"],),
    )
    total_row = await cursor2.fetchone()

    analyses = [await _row_to_response(db, dict(row), current_user) for row in rows]
    return TextAnalysisHistoryResponse(analyses=analyses, total=dict(total_row)["cnt"])
