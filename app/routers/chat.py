from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from app.db.session import get_db
from app.models import Conversation, ConversationMember, Message, ConversationType
from app.config.schemas import CreateDMRequest, CreateGroupRequest, SendMessageRequest, GroupModify, AddUserToGroupRequest
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.websocket_manager import manager
from sqlalchemy.exc import SQLAlchemyError
from app.utils.helpers import authenticate_ws, check_user_exists, get_current_user

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
    receiver, user_exists = await check_user_exists(payload.receiver_username, db)
    if not user_exists:
        raise HTTPException(status_code=404, detail="Receiver user not found")
    result = await db.execute(
        select(ConversationMember.conversation_id)
        .where(ConversationMember.user_id == auth_user.id)
        .intersect(
            select(ConversationMember.conversation_id)
            .where(ConversationMember.user_id == receiver.id)
        )
    )
    existing = result.scalars().first()
    if existing:
        return {"conversation_id": existing, "message": "DM already exists"}

    conversation = Conversation(type=ConversationType.DM)
    db.add(conversation)
    await db.flush()

    db.add(ConversationMember(conversation_id=conversation.id, user_id=auth_user.id))
    db.add(ConversationMember(conversation_id=conversation.id, user_id=receiver.id))

    await db.commit()
    return {"conversation_id": str(conversation.id), "type": "dm"}

@router.post("/conversations/group")
async def create_group(payload: CreateGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):

    if len(payload.members_username) == 0:
        raise HTTPException(status_code=400, detail="You have to add at least one user to the group")

    conversation = Conversation(type=ConversationType.GROUP, name=payload.name, created_by=auth_user.id)
    db.add(conversation)
    await db.flush()
    db.add(ConversationMember(conversation_id=conversation.id, user_id=auth_user.id, is_user_admin=True))

    existing_member_ids = set((await db.execute(
        select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation.id)
    )).scalars().all())

    not_users = []
    for member in payload.members_username:
        data, user_exists = await check_user_exists(member.strip(), db)
        if not user_exists:
            not_users.append(member)
            continue
        if data.id == auth_user.id:
            continue
        db.add(ConversationMember(conversation_id=conversation.id, user_id=data.id))

    await db.commit()
    await db.refresh(conversation)
    return {"conversation_id": conversation.id, "type": "group", "name": conversation.name, "created_by": auth_user.username, "admin": True, "users_who_dont_exist": not_users,}


@router.post("/conversations/{conversation_id}/group")
async def add_user_to_group(payload: AddUserToGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user), conversation_id: UUID = None):
    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    conversation = await db.get(Conversation, conversation_id)
    if not conversation or conversation.type != ConversationType.GROUP:
        raise HTTPException(status_code=404, detail="Group conversation not found")

    existing_member_ids = set((await db.execute(
        select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation_id)
    )).scalars().all())

    not_users = []
    already_members = []
    added = []
    for member in payload.members_username:
        data, user_exists = await check_user_exists(member.strip(), db)
        if not user_exists:
            not_users.append(member)
            continue
        if data.id in existing_member_ids:
            already_members.append(member)
            continue
        db.add(ConversationMember(conversation_id=conversation.id, user_id=data.id))
        existing_member_ids.add(data.id)
        added.append(member)

    await db.commit()
    await db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "type": "group",
        "name": conversation.name,
        "added": added,
        "users_who_dont_exist": not_users,
        "already_members": already_members,
    }


@router.post("/conversations/modify/changeName")
async def change_group_name(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == payload.group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")
    
    conversation_obj = (await db.execute(select(Conversation).where(Conversation.id==membership.conversation_id))).scalar_one_or_none()
    conversation_obj.name = payload.new_name
    await db.commit()
    await db.refresh(conversation_obj)
    return {"conversation_id": conversation_obj.id, "type": "group", "name": conversation_obj.name, "created_by": auth_user.username, "admin": True}

@router.post("/conversations/modify/removeUser")
async def remove_user_from_group(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    if not payload.target_user_id:
        raise HTTPException(status_code=400, detail="target_user_id is required")

    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == payload.group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    if payload.target_user_id == auth_user.id:
        raise HTTPException(status_code=400, detail="Admins cannot remove themselves; transfer admin or delete the group instead")

    target = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == payload.group_id,
                ConversationMember.user_id == payload.target_user_id,
            )
        )
    )).scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="The user to be deleted isn't in your group")

    db.delete(target)
    await db.commit()
    return {"conversation_id": str(payload.group_id), "removedtarget_user_id": str(payload.target_user_id)}


@router.post("/conversations/modify/makeAdmin")
async def make_another_user_admin(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    if not payload.target_user_id:
        raise HTTPException(status_code=400, detail="target_user_id is required")

    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == payload.group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    target = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == payload.group_id,
                ConversationMember.user_id == payload.target_user_id,
            )
        )
    )).scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="That user isn't in your group")

    target.is_user_admin = True
    await db.commit()
    return {"conversation_id": str(payload.group_id), "user_id": str(payload.target_user_id), "is_admin": True}
