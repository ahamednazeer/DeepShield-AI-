from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db
from models import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from services.audit import log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _resolve_new_user_role(db: aiosqlite.Connection) -> str:
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    existing_count = (await cursor.fetchone())[0]
    return "admin" if existing_count == 0 else "analyst"


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (req.username, req.email),
    )
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="Username or email already exists")

    hashed = hash_password(req.password)
    role = await _resolve_new_user_role(db)
    cursor = await db.execute(
        """INSERT INTO users (username, email, password_hash, role, status, last_login_at)
           VALUES (?, ?, ?, ?, 'active', ?)""",
        (req.username, req.email, hashed, role, datetime.now(timezone.utc).isoformat()),
    )
    await log_event(
        db,
        action="user_registered",
        target_type="user",
        target_id=cursor.lastrowid,
        actor_user_id=cursor.lastrowid,
        details={"role": role},
    )
    await db.commit()
    user_id = cursor.lastrowid

    token = create_token(user_id, req.username, role)
    return TokenResponse(
        access_token=token,
        user={
            "id": user_id,
            "username": req.username,
            "email": req.email,
            "role": role,
            "status": "active",
        },
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    cursor = await db.execute("SELECT * FROM users WHERE username = ?", (req.username,))
    user = await cursor.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = dict(user)
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("status", "active") != "active":
        raise HTTPException(status_code=403, detail="User account is suspended")

    await db.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user["id"]),
    )
    await log_event(
        db,
        action="user_logged_in",
        target_type="user",
        target_id=user["id"],
        actor_user_id=user["id"],
    )
    await db.commit()

    token = create_token(user["id"], user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "status": user.get("status", "active"),
        },
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        role=current_user["role"],
        status=current_user.get("status", "active"),
        created_at=str(current_user["created_at"]),
    )
