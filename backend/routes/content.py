from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_db
from services.audit import log_event
from services.content import build_unified_history, get_content_record, get_moderation_record
from services.moderation import create_share_link, resolve_permissions, to_moderation_state
from services.verdicts import normalize_verdict

router = APIRouter(prefix="/api", tags=["content"])


@router.get("/history/unified")
async def unified_history(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    items = await build_unified_history(db, current_user, include_all=False)
    return {"items": items, "total": len(items)}


@router.post("/content/{content_type}/{content_id}/share-link")
async def generate_share_link(
    content_type: str,
    content_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if content_type not in {"media", "text", "link"}:
        raise HTTPException(status_code=400, detail="Unsupported content type")

    record = await get_content_record(db, content_type, content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")
    if current_user["role"] != "admin" and record["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    moderation = await get_moderation_record(db, content_type, content_id)
    verdict = record.get("verdict")
    permissions = resolve_permissions(current_user, verdict, moderation, record.get("status"))
    if not permissions["can_share"]:
        raise HTTPException(status_code=403, detail=permissions["blocked_reason"] or "Sharing disabled")

    shared = await create_share_link(db, content_type, content_id, current_user["id"])
    await log_event(
        db,
        action="share_link_generated",
        target_type=content_type,
        target_id=content_id,
        actor_user_id=current_user["id"],
        details={"token": shared["token"]},
    )
    await db.commit()
    return {
        "share_url": f"/shared/{shared['token']}",
        "token": shared["token"],
        "expires_at": shared["expires_at"],
    }


@router.get("/public/share/{token}")
async def get_public_share(
    token: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT * FROM shared_links WHERE token = ? AND revoked_at IS NULL",
        (token,),
    )
    link = await cursor.fetchone()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    link = dict(link)

    if link.get("expires_at"):
        expires_at = datetime.fromisoformat(str(link["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share link expired")

    record = await get_content_record(db, link["content_type"], link["content_id"])
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")

    moderation = await get_moderation_record(db, link["content_type"], link["content_id"])
    permissions = resolve_permissions({"role": "viewer"}, record.get("verdict"), moderation, record.get("status"))
    if not permissions["can_share"]:
        raise HTTPException(status_code=403, detail="Shared access is no longer allowed")

    if link["content_type"] == "media":
        title = record["original_filename"]
        summary = {
            "type": "media",
            "title": title,
            "status": record["status"],
            "verdict": normalize_verdict(
                moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else record.get("verdict")
            ),
            "score": record.get("overall_score"),
            "created_at": str(record.get("created_at")),
            "moderation": to_moderation_state(moderation),
        }
    elif link["content_type"] == "text":
        text = " ".join(record.get("input_text", "").split())
        summary = {
            "type": "text",
            "title": text[:96] + ("…" if len(text) > 96 else ""),
            "status": record["status"],
            "verdict": normalize_verdict(
                moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else record.get("verdict")
            ),
            "score": record.get("final_score"),
            "created_at": str(record.get("created_at")),
            "excerpt": text[:420] + ("…" if len(text) > 420 else ""),
            "moderation": to_moderation_state(moderation),
        }
    else:
        summary = {
            "type": "link",
            "title": record.get("domain") or record.get("normalized_url") or record.get("input_url"),
            "status": record["status"],
            "verdict": normalize_verdict(
                moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else record.get("verdict")
            ),
            "score": record.get("risk_score"),
            "created_at": str(record.get("created_at")),
            "excerpt": record.get("final_url") or record.get("normalized_url") or record.get("input_url"),
            "final_url": record.get("final_url"),
            "moderation": to_moderation_state(moderation),
        }

    return {"token": token, "expires_at": link["expires_at"], "content": summary}
