import json
from typing import Any, Optional

import aiosqlite


async def log_event(
    db: aiosqlite.Connection,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
):
    await db.execute(
        """INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (
            actor_user_id,
            action,
            target_type,
            target_id,
            json.dumps(details or {}),
        ),
    )


async def fetch_audit_trail(
    db: aiosqlite.Connection,
    target_type: str,
    target_id: int,
    limit: int = 25,
) -> list[dict]:
    cursor = await db.execute(
        """SELECT audit_logs.*, users.username AS actor_username
           FROM audit_logs
           LEFT JOIN users ON users.id = audit_logs.actor_user_id
           WHERE audit_logs.target_type = ? AND audit_logs.target_id = ?
           ORDER BY audit_logs.created_at DESC
           LIMIT ?""",
        (target_type, target_id, limit),
    )
    rows = await cursor.fetchall()
    results = []
    for row in rows:
        payload = dict(row)
        try:
            payload["details"] = json.loads(payload.get("details") or "{}")
        except (json.JSONDecodeError, TypeError):
            payload["details"] = {}
        results.append(payload)
    return results


async def fetch_recent_activity(db: aiosqlite.Connection, limit: int = 30) -> list[dict]:
    cursor = await db.execute(
        """SELECT audit_logs.*, users.username AS actor_username
           FROM audit_logs
           LEFT JOIN users ON users.id = audit_logs.actor_user_id
           ORDER BY audit_logs.created_at DESC
           LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    activity = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.get("details") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["details"] = {}
        activity.append(item)
    return activity
