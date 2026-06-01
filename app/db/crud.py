from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.user import User
from app.db.session import get_db
from app.utils.helpers import *

class UserCrud:
    @staticmethod
    async def create_user(db: AsyncSession, user_data: dict):
        result = await db.execute(
            select(User).where(
                or_(
                    User.email == user_data.get("email"),
                    User.username == user_data.get("username"),
                )
            )
        )
        if result.scalars().first():
            return {"response": "this user already exists", "status": "failed"}

        passwordHash = hash_password(user_data.get("password"))
        user = User(
            email=user_data.get("email"),
            username=user_data.get("username"),
            name=user_data.get("name"),
            password=passwordHash,
        )
        db.add(user)

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user(db: AsyncSession, username:str):
        result = await db.execute(select(User).where(User.username==username))
        return result.scalar_one_or_none()

    @staticmethod
    async def change_password(db: AsyncSession, username:str, new_password: str):
        result = await db.execute(select(User).where(User.username==username))
        if not result.scalars().first():
            return {"response": "user not found", "status": "failed"}
        
        passwordHash = hash_password(new_password)
        user = result.scalars().first()
        user.password = passwordHash
        await db.commit()
        return {"response": "password changed successfully", "status": "success"}

    @staticmethod
    async def login(db: AsyncSession, username: str, password: str):
        user = await UserCrud.get_user(db, username)
        if not user or not verify_password(password, user.password):
            return {"response": "invalid username or password", "status": "failed"}
        return {"response": "login successful", "status": "success", "user": user}