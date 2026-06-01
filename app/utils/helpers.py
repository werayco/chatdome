from datetime import datetime, timedelta, timezone
from uuid import UUID
import bcrypt
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.settings import settings
from app.db.session import get_db
from fastapi import WebSocket
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


bearer_scheme = HTTPBearer()

async def authenticate_ws(websocket: WebSocket, db: AsyncSession):
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        user_id = UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def check_user_exists(username: str, db: AsyncSession):
    normalized_username = username.strip().lower()
    print(f"checking if user exists with username: {normalized_username}")
    result = await db.execute(select(User).where(User.username == normalized_username))
    data = result.scalar_one_or_none()
    user_exists = data is not None
    print(f"user exists: {user_exists}")
    return data, user_exists

async def get_receiever_id_by_username(username: str, db: AsyncSession):
    normalized_username = username.strip().lower()
    result = await db.execute(select(User).where(User.username == normalized_username))
    user = result.scalar_one_or_none()
    return user.id if user else None

async def authenticate_endpoints(token: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: AsyncSession = Depends(get_db)):
    if not token:
        return {"response": "token missing", "status": "failed"}
    try:
        payload = jwt.decode(token.credentials, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return {"response": "invalid or expired token", "status": "failed"}
        user_id = UUID(payload["sub"])

    except (JWTError, ValueError, KeyError):
        return {"response": "invalid or expired token", "status": "failed"}
    
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        
        return {"response": "user not found", "status": "failed"}
    else:
        return {"response": "authentication successful", "status": "success"}


async def get_current_user(token: HTTPAuthorizationCredentials = Depends(bearer_scheme),db: AsyncSession = Depends(get_db),) -> User:
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token.credentials, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise credentials_exception
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

def _build_token(user: User, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def issue_access_token(user: User) -> str:
    return _build_token(user, "access", timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def issue_refresh_token(user: User) -> str:
    return _build_token(user, "refresh", timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


async def get_user_from_refresh_token(
    refresh_token: str,
    db: AsyncSession,
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id = UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise credentials_exception
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    password_bytes = password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')    
    return bcrypt.checkpw(password_bytes, hashed_bytes)