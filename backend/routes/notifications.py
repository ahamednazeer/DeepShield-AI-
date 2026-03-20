import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        """SELECT * FROM notifications
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT 100""",
        (current_user["id"],),
    )
    notifications = [dict(row) for row in await cursor.fetchall()]

    cursor = await db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (current_user["id"],),
    )
    unread_count = (await cursor.fetchone())[0]
    return {"notifications": notifications, "unread_count": unread_count}


@router.get("/unread-count")
async def unread_count(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (current_user["id"],),
    )
    return {"unread_count": (await cursor.fetchone())[0]}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        "SELECT id FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, current_user["id"]),
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.execute(
        "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ?",
        (notification_id,),
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND read_at IS NULL",
        (current_user["id"],),
    )
    await db.commit()
    return {"status": "ok"}
