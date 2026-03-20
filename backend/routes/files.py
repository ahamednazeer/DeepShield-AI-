from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from auth import get_current_user, get_request_user
from config import EVIDENCE_DIR, UPLOAD_DIR
from database import get_db
from services.audit import log_event
from services.moderation import resolve_permissions

router = APIRouter(prefix="/api/files", tags=["files"])


async def _resolve_request_user(
    request: Request,
    db: aiosqlite.Connection,
    token: str | None,
) -> dict:
    return await get_request_user(request, db, token=token)


def _safe_path(base_dir: Path, filename: str) -> Path:
    candidate = (base_dir / filename).resolve()
    if base_dir.resolve() not in candidate.parents and candidate != base_dir.resolve():
        raise HTTPException(status_code=400, detail="Invalid file path")
    return candidate


@router.get("/upload/{filename:path}")
async def get_upload_file(
    filename: str,
    request: Request,
    token: str | None = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    current_user = await _resolve_request_user(request, db, token)
    cursor = await db.execute("SELECT * FROM analyses WHERE filename = ?", (filename,))
    analysis = await cursor.fetchone()
    if not analysis:
        raise HTTPException(status_code=404, detail="File not found")
    analysis = dict(analysis)
    if current_user["role"] != "admin" and analysis["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    file_path = _safe_path(UPLOAD_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@router.get("/evidence/{filename:path}")
async def get_evidence_file(
    filename: str,
    request: Request,
    token: str | None = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    current_user = await _resolve_request_user(request, db, token)
    cursor = await db.execute(
        """SELECT analyses.user_id
           FROM evidence_items
           JOIN analyses ON analyses.id = evidence_items.analysis_id
           WHERE evidence_items.file_path = ?""",
        (filename,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if current_user["role"] != "admin" and row[0] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    file_path = _safe_path(EVIDENCE_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence not found")
    return FileResponse(file_path)


@router.get("/media/{analysis_id}/download")
async def download_media(
    analysis_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if current_user["role"] == "admin":
        cursor = await db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    else:
        cursor = await db.execute(
            "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"]),
        )
    analysis = await cursor.fetchone()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis = dict(analysis)

    cursor = await db.execute(
        "SELECT * FROM content_moderation WHERE content_type = 'media' AND content_id = ?",
        (analysis_id,),
    )
    moderation_row = await cursor.fetchone()
    moderation = dict(moderation_row) if moderation_row else None
    permissions = resolve_permissions(current_user, analysis.get("verdict"), moderation, analysis.get("status"))
    if not permissions["can_download"]:
        raise HTTPException(status_code=403, detail=permissions["blocked_reason"] or "Downloads disabled")

    file_path = _safe_path(UPLOAD_DIR, analysis["filename"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    await log_event(
        db,
        action="media_downloaded",
        target_type="media",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
    )
    await db.commit()
    return FileResponse(
        file_path,
        filename=analysis["original_filename"],
        media_type="application/octet-stream",
    )
