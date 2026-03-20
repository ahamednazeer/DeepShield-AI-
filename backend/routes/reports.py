from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
import aiosqlite

from auth import get_current_user
from database import get_db
from services.audit import log_event
from services.reports import build_media_report, render_report_pdf

router = APIRouter(prefix="/api", tags=["reports"])


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


@router.get("/reports/{analysis_id}")
async def get_report(
    analysis_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    analysis = await _fetch_analysis(db, analysis_id, current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not yet completed")

    report = await build_media_report(db, analysis, current_user)
    return JSONResponse(content=report)


@router.get("/reports/{analysis_id}/download")
async def download_report(
    analysis_id: int,
    format: str = Query("pdf", pattern="^(pdf|json)$"),
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    analysis = await _fetch_analysis(db, analysis_id, current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not yet completed")

    report = await build_media_report(db, analysis, current_user)
    await log_event(
        db,
        action="report_downloaded",
        target_type="media",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
        details={"format": format},
    )
    await db.commit()

    if format == "json":
        return Response(
            content=JSONResponse(content=report).body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="deepshield-report-{analysis_id}.json"'
            },
        )

    pdf_bytes = render_report_pdf(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="deepshield-report-{analysis_id}.pdf"'
        },
    )
