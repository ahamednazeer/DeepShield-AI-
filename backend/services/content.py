import json
from typing import Optional

import aiosqlite

from services.moderation import resolve_permissions, to_moderation_state
from services.verdicts import normalize_verdict


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


def _title_from_text(text: str, limit: int = 96) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


async def get_media_record(db: aiosqlite.Connection, analysis_id: int) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_text_record(db: aiosqlite.Connection, analysis_id: int) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM text_analyses WHERE id = ?", (analysis_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["claims"] = _parse_json(payload.get("claims"), [])
    payload["evidence"] = _parse_json(payload.get("evidence"), [])
    payload["explanation"] = _parse_json(payload.get("explanation"), {})
    payload["semantic_results"] = _parse_json(payload.get("semantic_results"), [])
    return payload


async def get_link_record(db: aiosqlite.Connection, analysis_id: int) -> Optional[dict]:
    cursor = await db.execute("SELECT * FROM link_analyses WHERE id = ?", (analysis_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["signals"] = _parse_json(payload.get("signals"), [])
    payload["provider_summary"] = _parse_json(payload.get("provider_summary"), {})
    payload["redirect_chain"] = _parse_json(payload.get("redirect_chain"), [])
    payload["page_metadata"] = _parse_json(payload.get("page_metadata"), {})
    return payload


async def get_content_record(
    db: aiosqlite.Connection,
    content_type: str,
    content_id: int,
) -> Optional[dict]:
    if content_type == "media":
        return await get_media_record(db, content_id)
    if content_type == "text":
        return await get_text_record(db, content_id)
    if content_type == "link":
        return await get_link_record(db, content_id)
    return None


async def get_moderation_record(
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


def build_unified_item(current_user: dict, content_type: str, record: dict, moderation: Optional[dict]) -> dict:
    if content_type == "media":
        verdict = record.get("verdict")
        score = record.get("overall_score")
        title = record.get("original_filename")
        kind = record.get("media_type")
        status = record.get("status")
        created_at = str(record.get("created_at"))
        completed_at = str(record.get("completed_at")) if record.get("completed_at") else None
        preview_text = record.get("original_filename")
    elif content_type == "text":
        verdict = record.get("verdict")
        score = record.get("final_score")
        title = _title_from_text(record.get("input_text", ""))
        kind = "text"
        status = record.get("status")
        created_at = str(record.get("created_at"))
        completed_at = str(record.get("completed_at")) if record.get("completed_at") else None
        preview_text = _title_from_text(record.get("input_text", ""), 140)
    else:
        verdict = record.get("verdict")
        score = record.get("risk_score")
        title = record.get("domain") or record.get("normalized_url") or record.get("input_url")
        kind = "link"
        status = record.get("status")
        created_at = str(record.get("created_at"))
        completed_at = str(record.get("completed_at")) if record.get("completed_at") else None
        preview_text = record.get("final_url") or record.get("normalized_url") or record.get("input_url")

    effective_verdict = normalize_verdict(
        moderation.get("manual_verdict") if moderation and moderation.get("manual_verdict") else verdict
    )
    return {
        "id": f"{content_type}-{record['id']}",
        "content_type": content_type,
        "content_id": record["id"],
        "title": title,
        "kind": kind,
        "status": status,
        "verdict": verdict,
        "effective_verdict": effective_verdict,
        "score": score,
        "created_at": created_at,
        "completed_at": completed_at,
        "processing_time": record.get("processing_time"),
        "preview_text": preview_text,
        "permissions": resolve_permissions(current_user, verdict, moderation, status),
        "moderation": to_moderation_state(moderation),
    }


async def build_unified_history(
    db: aiosqlite.Connection,
    current_user: dict,
    include_all: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    media_query = "SELECT * FROM analyses"
    text_query = "SELECT * FROM text_analyses"
    link_query = "SELECT * FROM link_analyses"
    media_args = []
    text_args = []
    link_args = []

    if not include_all:
        media_query += " WHERE user_id = ?"
        text_query += " WHERE user_id = ?"
        link_query += " WHERE user_id = ?"
        media_args.append(current_user["id"])
        text_args.append(current_user["id"])
        link_args.append(current_user["id"])

    media_query += " ORDER BY created_at DESC"
    text_query += " ORDER BY created_at DESC"
    link_query += " ORDER BY created_at DESC"

    cursor = await db.execute(media_query, tuple(media_args))
    media_rows = [dict(row) for row in await cursor.fetchall()]
    cursor = await db.execute(text_query, tuple(text_args))
    text_rows = [dict(row) for row in await cursor.fetchall()]
    cursor = await db.execute(link_query, tuple(link_args))
    link_rows = [dict(row) for row in await cursor.fetchall()]

    items = []
    for row in media_rows:
        moderation = await get_moderation_record(db, "media", row["id"])
        items.append(build_unified_item(current_user, "media", row, moderation))

    for row in text_rows:
        moderation = await get_moderation_record(db, "text", row["id"])
        items.append(build_unified_item(current_user, "text", row, moderation))

    for row in link_rows:
        moderation = await get_moderation_record(db, "link", row["id"])
        items.append(build_unified_item(current_user, "link", row, moderation))

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    if limit is not None:
        return items[:limit]
    return items
