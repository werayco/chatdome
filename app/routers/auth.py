from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.schemas import (AccessTokenResponse,ChangePasswordRequest,LoginRequest,RefreshRequest,RegisterRequest,TokenResponse,UserResponse)
from app.db.crud import UserCrud
from app.db.session import get_db
from app.models.user import User
from app.utils.helpers import (get_current_user,get_user_from_refresh_token,hash_password,issue_access_token,issue_refresh_token,verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await UserCrud.create_user(db, payload.model_dump())
    if isinstance(result, dict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["response"])
    return TokenResponse(
        access_token=issue_access_token(result),
        refresh_token=issue_refresh_token(result),
        user=result,
    )

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await UserCrud.login(db, payload.username, payload.password)
    if result["status"] == "failed":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result["response"])
    user = result["user"]

    return TokenResponse(
        access_token=issue_access_token(user),
        refresh_token=issue_refresh_token(user),
        user=user,
    )

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_from_refresh_token(payload.refresh_token, db)
    return AccessTokenResponse(access_token=issue_access_token(user))

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )
    current_user.password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}
