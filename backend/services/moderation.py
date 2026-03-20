import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

from config import SHARE_LINK_TTL_HOURS
from services.verdicts import normalize_verdict

BLOCKED_VERDICTS = {"MANIPULATED"}
REVIEW_VERDICTS = {"MANIPULATED", "SUSPICIOUS"}


def _loads(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _default_actions(verdict: Optional[str]) -> list[str]:
    verdict = normalize_verdict(verdict)
    if verdict in BLOCKED_VERDICTS:
        return ["flag", "quarantine", "block_share", "block_download", "notify_admin", "review_queue"]
    if verdict in REVIEW_VERDICTS:
        return ["flag", "review_queue", "notify_admin"]
    return []


async def fetch_moderation(
    db: aiosqlite.Connection,
    content_type: str,
    content_id: int,
) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT * FROM content_moderation WHERE content_type = ? AND content_id = ?",
        (content_type, content_id),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def apply_moderation_rules(
    db: aiosqlite.Connection,
    content_type: str,
    content_id: int,
    owner_user_id: int,
    verdict: Optional[str],
    score: Optional[float],
) -> dict:
    verdict = normalize_verdict(verdict)
    cursor = await db.execute(
        """SELECT * FROM moderation_rules
           WHERE enabled = 1 AND (target_type = ? OR target_type = 'all')
           ORDER BY id ASC""",
        (content_type,),
    )
    rules = [dict(row) for row in await cursor.fetchall()]

    matched_rule_ids = []
    actions: set[str] = set()
    for rule in rules:
        verdict_match = normalize_verdict(rule.get("verdict_match"))
        min_score = rule.get("min_score")
        if verdict_match and verdict_match != verdict:
            continue
        if min_score is not None and score is None:
            continue
        if min_score is not None and score is not None and score < min_score:
            continue
        matched_rule_ids.append(rule["id"])
        actions.update(_loads(rule.get("actions"), []))

    if not actions:
        actions.update(_default_actions(verdict))

    existing = await fetch_moderation(db, content_type, content_id)
    manual_verdict = existing.get("manual_verdict") if existing else None
    review_status = existing.get("review_status", "clear") if existing else "clear"
    if review_status != "reviewed":
        review_status = "pending_review" if "review_queue" in actions else "clear"

    payload = {
        "effective_verdict": normalize_verdict(manual_verdict or verdict),
        "auto_actions": json.dumps(sorted(actions)),
        "is_flagged": 1 if "flag" in actions else 0,
        "is_quarantined": 1 if "quarantine" in actions else 0,
        "share_blocked": 1 if "block_share" in actions or normalize_verdict(manual_verdict or verdict) in BLOCKED_VERDICTS else 0,
        "download_blocked": 1 if "block_download" in actions or normalize_verdict(manual_verdict or verdict) in BLOCKED_VERDICTS else 0,
        "review_status": review_status,
    }

    if existing:
        await db.execute(
            """UPDATE content_moderation
               SET effective_verdict = ?, auto_actions = ?, is_flagged = ?, is_quarantined = ?,
                   share_blocked = ?, download_blocked = ?, review_status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE content_type = ? AND content_id = ?""",
            (
                payload["effective_verdict"],
                payload["auto_actions"],
                payload["is_flagged"],
                payload["is_quarantined"],
                payload["share_blocked"],
                payload["download_blocked"],
                payload["review_status"],
                content_type,
                content_id,
            ),
        )
    else:
        await db.execute(
            """INSERT INTO content_moderation
               (content_type, content_id, owner_user_id, effective_verdict, auto_actions,
                is_flagged, is_quarantined, share_blocked, download_blocked, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                content_type,
                content_id,
                owner_user_id,
                payload["effective_verdict"],
                payload["auto_actions"],
                payload["is_flagged"],
                payload["is_quarantined"],
                payload["share_blocked"],
                payload["download_blocked"],
                payload["review_status"],
            ),
        )

    moderation = await fetch_moderation(db, content_type, content_id)
    moderation["matched_rule_ids"] = matched_rule_ids
    moderation["auto_actions"] = _loads(moderation.get("auto_actions"), [])
    return moderation


async def create_notification(
    db: aiosqlite.Connection,
    user_id: int,
    title: str,
    message: str,
    severity: str = "info",
    kind: str = "system",
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
):
    await db.execute(
        """INSERT INTO notifications
           (user_id, title, message, severity, kind, target_type, target_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, title, message, severity, kind, target_type, target_id),
    )


async def notify_admins(
    db: aiosqlite.Connection,
    title: str,
    message: str,
    severity: str = "warning",
    kind: str = "alert",
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
):
    cursor = await db.execute("SELECT id FROM users WHERE role = 'admin' AND status = 'active'")
    admins = await cursor.fetchall()
    for admin in admins:
        await create_notification(
            db,
            admin[0],
            title,
            message,
            severity=severity,
            kind=kind,
            target_type=target_type,
            target_id=target_id,
        )


def to_moderation_state(row: Optional[dict]) -> dict:
    if not row:
        return {
            "is_flagged": False,
            "is_quarantined": False,
            "review_status": "clear",
            "manual_verdict": None,
            "review_notes": None,
            "auto_actions": [],
            "reviewed_by": None,
            "reviewed_at": None,
        }
    return {
        "is_flagged": bool(row.get("is_flagged")),
        "is_quarantined": bool(row.get("is_quarantined")),
        "review_status": row.get("review_status") or "clear",
        "manual_verdict": row.get("manual_verdict"),
        "review_notes": row.get("review_notes"),
        "auto_actions": _loads(row.get("auto_actions"), []),
        "reviewed_by": row.get("reviewed_by"),
        "reviewed_at": str(row["reviewed_at"]) if row.get("reviewed_at") else None,
    }


def resolve_permissions(
    current_user: dict,
    verdict: Optional[str],
    moderation_row: Optional[dict],
    status: Optional[str] = None,
) -> dict:
    effective_verdict = normalize_verdict(
        moderation_row.get("manual_verdict") if moderation_row and moderation_row.get("manual_verdict") else verdict
    )
    blocked_reason = None
    share_blocked = bool(moderation_row.get("share_blocked")) if moderation_row else False
    download_blocked = bool(moderation_row.get("download_blocked")) if moderation_row else False
    quarantined = bool(moderation_row.get("is_quarantined")) if moderation_row else False
    review_status = (moderation_row.get("review_status") if moderation_row else None) or "clear"

    if effective_verdict in BLOCKED_VERDICTS:
        share_blocked = True
        download_blocked = True
        blocked_reason = "Detected as harmful or fake content"
    if quarantined:
        share_blocked = True
        download_blocked = True
        if review_status == "pending_review":
            blocked_reason = "Content is quarantined pending review"
        else:
            blocked_reason = "Content remains quarantined after admin review"
    if status and status != "completed":
        share_blocked = True
        download_blocked = True
        blocked_reason = "Analysis is still waiting for final provider results"

    can_download = not download_blocked
    if current_user.get("role") == "admin":
        can_download = True
        if blocked_reason:
            blocked_reason = f"{blocked_reason}. Admin override is available for downloads."

    can_share = not share_blocked
    return {
        "can_view": True,
        "can_download": can_download,
        "can_share": can_share,
        "blocked_reason": blocked_reason,
    }


async def moderate_content(
    db: aiosqlite.Connection,
    content_type: str,
    content_id: int,
    owner_user_id: int,
    base_verdict: Optional[str],
    reviewer_id: int,
    review_status: Optional[str] = None,
    manual_verdict: Optional[str] = None,
    review_notes: Optional[str] = None,
    is_flagged: Optional[bool] = None,
    is_quarantined: Optional[bool] = None,
    block_share: Optional[bool] = None,
    block_download: Optional[bool] = None,
) -> dict:
    base_verdict = normalize_verdict(base_verdict)
    manual_verdict = normalize_verdict(manual_verdict) or None
    review_status = review_status or None
    review_notes = review_notes if review_notes not in ("", None) else None
    existing = await fetch_moderation(db, content_type, content_id)
    if not existing:
        await apply_moderation_rules(db, content_type, content_id, owner_user_id, base_verdict, None)
        existing = await fetch_moderation(db, content_type, content_id)

    final_verdict = normalize_verdict(manual_verdict or existing.get("manual_verdict") or base_verdict)
    final_review_status = review_status or existing.get("review_status") or "clear"
    final_flag = existing.get("is_flagged", 0) if is_flagged is None else int(is_flagged)
    final_quarantine = existing.get("is_quarantined", 0) if is_quarantined is None else int(is_quarantined)

    if manual_verdict in BLOCKED_VERDICTS:
        final_quarantine = 1
        if block_share is None:
            block_share = True
        if block_download is None:
            block_download = True
    elif manual_verdict and manual_verdict not in BLOCKED_VERDICTS and not final_quarantine:
        if block_share is None:
            block_share = False
        if block_download is None:
            block_download = False

    final_share_blocked = existing.get("share_blocked", 0) if block_share is None else int(block_share)
    final_download_blocked = existing.get("download_blocked", 0) if block_download is None else int(block_download)

    await db.execute(
        """UPDATE content_moderation
           SET effective_verdict = ?, is_flagged = ?, is_quarantined = ?, share_blocked = ?,
               download_blocked = ?, review_status = ?, manual_verdict = ?, review_notes = ?,
               reviewed_by = ?, reviewed_at = ?, updated_at = CURRENT_TIMESTAMP
           WHERE content_type = ? AND content_id = ?""",
        (
            final_verdict,
            final_flag,
            final_quarantine,
            final_share_blocked,
            final_download_blocked,
            final_review_status,
            manual_verdict if manual_verdict is not None else existing.get("manual_verdict"),
            review_notes if review_notes is not None else existing.get("review_notes"),
            reviewer_id,
            datetime.now(timezone.utc).isoformat(),
            content_type,
            content_id,
        ),
    )

    return await fetch_moderation(db, content_type, content_id)


async def create_share_link(
    db: aiosqlite.Connection,
    content_type: str,
    content_id: int,
    created_by: int,
) -> dict:
    token = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SHARE_LINK_TTL_HOURS)
    await db.execute(
        """INSERT INTO shared_links (token, content_type, content_id, created_by, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (token, content_type, content_id, created_by, expires_at.isoformat()),
    )
    return {"token": token, "expires_at": expires_at.isoformat()}
