import json

import aiosqlite
from fastapi import APIRouter, Body, Depends, HTTPException

from auth import require_admin
from database import get_db
from services.audit import fetch_recent_activity, log_event
from services.content import build_unified_history, get_content_record, get_moderation_record
from services.moderation import moderate_content

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
async def admin_overview(
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    total_users = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active_users = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE status != 'active'")
    suspended_users = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM analyses")
    total_media = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM text_analyses")
    total_text = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM link_analyses")
    total_links = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM content_moderation WHERE is_flagged = 1")
    flagged_content = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM content_moderation WHERE is_quarantined = 1")
    quarantined_content = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM content_moderation WHERE review_status = 'pending_review'")
    review_queue = (await cursor.fetchone())[0]
    cursor = await db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (current_user["id"],))
    unread_admin_notifications = (await cursor.fetchone())[0]

    unified = await build_unified_history(db, current_user, include_all=True, limit=12)
    flagged_items = [
        item
        for item in unified
        if item["moderation"]["is_flagged"] or item["moderation"]["review_status"] == "pending_review"
    ][:8]

    activity = await fetch_recent_activity(db, limit=20)
    cursor = await db.execute("SELECT * FROM moderation_rules ORDER BY id ASC")
    rules = []
    for row in await cursor.fetchall():
        item = dict(row)
        try:
            item["actions"] = json.loads(item.get("actions") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["actions"] = []
        rules.append(item)

    return {
        "counts": {
            "total_users": total_users,
            "active_users": active_users,
            "suspended_users": suspended_users,
            "total_media": total_media,
            "total_text": total_text,
            "total_links": total_links,
            "flagged_content": flagged_content,
            "quarantined_content": quarantined_content,
            "review_queue": review_queue,
            "unread_admin_notifications": unread_admin_notifications,
        },
        "flagged_items": flagged_items,
        "recent_activity": activity,
        "rules": rules,
    }


@router.get("/users")
async def admin_users(
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        """SELECT users.*,
                  (SELECT COUNT(*) FROM analyses WHERE analyses.user_id = users.id) AS media_count,
                  (SELECT COUNT(*) FROM text_analyses WHERE text_analyses.user_id = users.id) AS text_count,
                  (SELECT COUNT(*) FROM link_analyses WHERE link_analyses.user_id = users.id) AS link_count
           FROM users
           ORDER BY users.created_at DESC"""
    )
    users = [dict(row) for row in await cursor.fetchall()]
    return {"users": users}


@router.post("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: dict = Body(...),
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    status = payload.get("status")
    if status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="Unsupported status")
    if user_id == current_user["id"] and status != "active":
        raise HTTPException(status_code=400, detail="You cannot suspend your own account")

    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    await log_event(
        db,
        action="user_status_updated",
        target_type="user",
        target_id=user_id,
        actor_user_id=current_user["id"],
        details={"status": status},
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/rules")
async def list_rules(
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute("SELECT * FROM moderation_rules ORDER BY id ASC")
    rules = []
    for row in await cursor.fetchall():
        payload = dict(row)
        try:
            payload["actions"] = json.loads(payload.get("actions") or "[]")
        except (json.JSONDecodeError, TypeError):
            payload["actions"] = []
        rules.append(payload)
    return {"rules": rules}


@router.post("/rules")
async def create_rule(
    payload: dict = Body(...),
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    actions = payload.get("actions") or []
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Rule name is required")
    if payload.get("target_type") not in {"all", "media", "text", "link"}:
        raise HTTPException(status_code=400, detail="Unsupported target type")

    cursor = await db.execute(
        """INSERT INTO moderation_rules
           (name, description, target_type, verdict_match, min_score, actions, enabled, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload["name"],
            payload.get("description"),
            payload.get("target_type", "all"),
            payload.get("verdict_match"),
            payload.get("min_score"),
            json.dumps(actions),
            1 if payload.get("enabled", True) else 0,
            current_user["id"],
        ),
    )
    await log_event(
        db,
        action="moderation_rule_created",
        target_type="rule",
        target_id=cursor.lastrowid,
        actor_user_id=current_user["id"],
        details={"name": payload["name"]},
    )
    await db.commit()
    return {"status": "ok", "id": cursor.lastrowid}


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    payload: dict = Body(...),
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute("SELECT id FROM moderation_rules WHERE id = ?", (rule_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.execute(
        """UPDATE moderation_rules
           SET name = ?, description = ?, target_type = ?, verdict_match = ?, min_score = ?,
               actions = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (
            payload.get("name"),
            payload.get("description"),
            payload.get("target_type", "all"),
            payload.get("verdict_match"),
            payload.get("min_score"),
            json.dumps(payload.get("actions") or []),
            1 if payload.get("enabled", True) else 0,
            rule_id,
        ),
    )
    await log_event(
        db,
        action="moderation_rule_updated",
        target_type="rule",
        target_id=rule_id,
        actor_user_id=current_user["id"],
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute("DELETE FROM moderation_rules WHERE id = ?", (rule_id,))
    await log_event(
        db,
        action="moderation_rule_deleted",
        target_type="rule",
        target_id=rule_id,
        actor_user_id=current_user["id"],
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/review-queue")
async def review_queue(
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    items = await build_unified_history(db, current_user, include_all=True)
    queue = [
        item
        for item in items
        if item["moderation"]["review_status"] == "pending_review"
    ]
    return {"items": queue}


@router.post("/content/{content_type}/{content_id}/moderate")
async def moderate_queue_item(
    content_type: str,
    content_id: int,
    payload: dict = Body(...),
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if content_type not in {"media", "text", "link"}:
        raise HTTPException(status_code=400, detail="Unsupported content type")

    record = await get_content_record(db, content_type, content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Content not found")
    moderation = await moderate_content(
        db,
        content_type=content_type,
        content_id=content_id,
        owner_user_id=record["user_id"],
        base_verdict=record.get("verdict"),
        reviewer_id=current_user["id"],
        review_status=payload.get("review_status"),
        manual_verdict=payload.get("manual_verdict"),
        review_notes=payload.get("review_notes"),
        is_flagged=payload.get("is_flagged"),
        is_quarantined=payload.get("is_quarantined"),
        block_share=payload.get("block_share"),
        block_download=payload.get("block_download"),
    )
    await log_event(
        db,
        action="content_moderated",
        target_type=content_type,
        target_id=content_id,
        actor_user_id=current_user["id"],
        details={
            "review_status": payload.get("review_status"),
            "manual_verdict": payload.get("manual_verdict"),
        },
    )
    await db.commit()
    return {"status": "ok", "moderation": moderation}
