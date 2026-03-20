from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import JWT_ALGORITHM, JWT_EXPIRATION_HOURS, JWT_SECRET
from database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_user_by_id(db: aiosqlite.Connection, user_id: int) -> dict:
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = await cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user = dict(user)
    if user.get("status", "active") != "active":
        raise HTTPException(status_code=403, detail="User account is suspended")
    return user


async def get_user_from_token(token: str, db: aiosqlite.Connection) -> dict:
    payload = decode_token(token)
    return await get_user_by_id(db, int(payload["sub"]))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await get_user_from_token(credentials.credentials, db)


async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def get_request_user(
    request: Request,
    db: aiosqlite.Connection,
    token: Optional[str] = None,
) -> dict:
    auth_header = request.headers.get("Authorization", "")
    bearer_token = None
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()

    resolved_token = token or bearer_token
    if not resolved_token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    return await get_user_from_token(resolved_token, db)
