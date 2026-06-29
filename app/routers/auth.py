from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.schemas import (AccessTokenResponse,ChangePasswordRequest,LoginRequest,RefreshRequest,RegisterRequest,TokenResponse,UserResponse)
from app.db.crud import UserCrud
from app.db.session import get_db
from app.models.user import User
from app.utils.helpers import (get_current_user,get_user_from_refresh_token,hash_password,issue_access_token,issue_refresh_token,verify_password)
from app.controllers import AuthController

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await AuthController.register(payload, db)

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await AuthController.login(payload, db)

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_from_refresh_token(payload.refresh_token, db)
    return AccessTokenResponse(access_token=issue_access_token(user))

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest,current_user: User = Depends(get_current_user),db: AsyncSession = Depends(get_db),):
    return await AuthController.change_password(payload, current_user, db)