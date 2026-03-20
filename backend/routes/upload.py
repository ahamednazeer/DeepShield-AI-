import os
import uuid
import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import aiosqlite
from auth import get_current_user
from database import get_db
from config import (
    UPLOAD_DIR,
    MAX_FILE_SIZE_MB,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    ALL_ALLOWED_EXTENSIONS,
)
from services.audit import log_event

router = APIRouter(prefix="/api", tags=["upload"])


def classify_media(ext: str) -> str:
    ext = ext.lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        return "video"
    elif ext in ALLOWED_AUDIO_EXTENSIONS:
        return "audio"
    return "unknown"


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Validate extension
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()
    if ext not in ALL_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALL_ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Maximum: {MAX_FILE_SIZE_MB}MB",
        )

    # Save file
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as f:
        f.write(content)

    # Classify media type
    media_type = classify_media(ext)

    # Create analysis record
    cursor = await db.execute(
        """INSERT INTO analyses (user_id, filename, original_filename, media_type, file_size, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (current_user["id"], unique_name, original_name, media_type, len(content)),
    )
    analysis_id = cursor.lastrowid
    await log_event(
        db,
        action="media_uploaded",
        target_type="media",
        target_id=analysis_id,
        actor_user_id=current_user["id"],
        details={"filename": original_name, "media_type": media_type},
    )
    await db.commit()

    return {
        "id": analysis_id,
        "filename": unique_name,
        "original_filename": original_name,
        "media_type": media_type,
        "file_size": len(content),
        "status": "pending",
    }
