from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from app.db.session import get_db
from app.models import Conversation, ConversationMember, Message, ConversationType, User
from app.config.schemas import CreateDMRequest, CreateGroupRequest, SendMessageRequest, GroupModify, AddUserToGroupRequest, RemoveUserFromGroupRequest
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.websocket_manager import manager
from app.controllers import ChatController
from sqlalchemy.exc import SQLAlchemyError
from app.utils.helpers import authenticate_ws, get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket,conversation_id: UUID,db: AsyncSession = Depends(get_db),):
    user = await authenticate_ws(websocket, db)

    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    member = (await db.execute(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id,ConversationMember.user_id == user.id,))).scalar_one_or_none()

    if not member:
        print(f"unauthorized connection attempt by user {user.username} to conversation {conversation_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="You're not a member of this conversation. You can create a DM with the user or ask the group admin to add you to the group.")
        return

    await manager.connect(conversation_id, websocket)
    try: 
        while True:
            payload = await websocket.receive_json()
            content = payload.get("content")
            if not content:
                continue

            new_message = Message(conversation_id=conversation_id,sender_id=user.id,content=content)
            db.add(new_message)

            try:
                await db.commit()
                await db.refresh(new_message)

            except SQLAlchemyError:
                await db.rollback()
                await websocket.send_json({"error": "Failed to save message"})
                continue

            await manager.broadcast(conversation_id, {
                "id": str(new_message.id),
                "conversation_id": str(conversation_id),
                "sender_id": str(user.id),
                "sender_username": user.username,
                "content": new_message.content,
                "created_at": new_message.created_at.isoformat(),
            })
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(conversation_id, websocket)

@router.post("/conversations/dm")
async def create_dm(payload: CreateDMRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.create_dm(payload, db, auth_user)

@router.post("/conversations/group")
async def create_group(payload: CreateGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.create_group(payload, db, auth_user)

@router.get("/conversations/getGroups")
async def get_user_groups(db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.get_user_groups(db, auth_user)

@router.post("/conversations/modify/addUser")
async def add_user_to_group(payload: AddUserToGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user), conversation_id: UUID = None):
    return await ChatController.add_user_to_group(payload, db, auth_user, conversation_id)

@router.post("/conversations/modify/changeName")
async def change_group_name(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.change_group_name(payload, db, auth_user)

@router.post("/conversations/modify/makeAdmin")
async def make_another_user_admin(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.get_all_group_users(payload, db, auth_user)

@router.post("/conversation/getUsersInConversation")
async def get_all_group_users(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    return await ChatController.get_all_group_users(payload, db, auth_user)
