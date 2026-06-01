from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

class GroupModify(BaseModel):
    group_id : UUID
    new_name: Optional[str] = None
    target_user_id: Optional[UUID] = None


class AddUserToGroupRequest(BaseModel):
    name: str
    member_ids: list[UUID] = None
    members_username: list[str]

class CreateDMRequest(BaseModel):
    receiver_username: str

class CreateGroupRequest(BaseModel):
    name: str
    member_ids: list[UUID] = None
    members_username: list[str]


class SendMessageRequest(BaseModel):
    sender_id: UUID
    content: str


class RegisterRequest(BaseModel):
    email: str
    name: str
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    name: str
    cover_url: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
