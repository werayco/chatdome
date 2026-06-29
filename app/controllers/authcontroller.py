from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.schemas import (AccessTokenResponse,ChangePasswordRequest,LoginRequest,RefreshRequest,RegisterRequest,TokenResponse,UserResponse)
from app.db.crud import UserCrud
from app.db.session import get_db
from app.models.user import User
from app.utils.helpers import (get_current_user,get_user_from_refresh_token,hash_password,issue_access_token,issue_refresh_token,verify_password)

class AuthController:
    @staticmethod
    async def register(payload: RegisterRequest, db: AsyncSession):
        result = await UserCrud.create_user(db, payload.model_dump())
        if isinstance(result, dict):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["response"])
        return TokenResponse(
            access_token=issue_access_token(result),
            refresh_token=issue_refresh_token(result),
            user=result,
        )

    @staticmethod
    async def login(payload: LoginRequest, db: AsyncSession):
        result = await UserCrud.login(db, payload.username, payload.password)
        if result["status"] == "failed":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result["response"])
        user = result["user"]

        return TokenResponse(
            access_token=issue_access_token(user),
            refresh_token=issue_refresh_token(user),
            user=user,
        )

    @staticmethod
    async def refresh(payload: RefreshRequest, db: AsyncSession):
        user = await get_user_from_refresh_token(payload.refresh_token, db)
        return AccessTokenResponse(access_token=issue_access_token(user))

    @staticmethod
    async def me(current_user: User):
        return current_user

    @staticmethod
    async def change_password(
        payload: ChangePasswordRequest,
        current_user: User,
        db: AsyncSession,
    ):
        if not verify_password(payload.old_password, current_user.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Old password is incorrect",
            )
        current_user.password = hash_password(payload.new_password)
        await db.commit()
        return {"message": "Password changed successfully"}