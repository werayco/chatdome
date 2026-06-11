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
from sqlalchemy.exc import SQLAlchemyError
from app.utils.helpers import authenticate_ws, check_user_exists, get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


async def _resolve_group_id(payload: GroupModify, db: AsyncSession) -> UUID:
    if not payload.group_name:
        raise HTTPException(status_code=400, detail="group_name is required")

    rows = (await db.execute(
        select(Conversation.id).where(
            and_(
                Conversation.name == payload.group_name.strip(),
                Conversation.type == ConversationType.GROUP,
            )
        )
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Group not found")
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple groups share that name; rename one so the name is unique",
        )
    return rows[0]

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


@router.get("/conversations/getGroups")
async def get_user_groups(db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    rows = (await db.execute(
    select(Conversation)
    .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
    .where(and_(ConversationMember.user_id == auth_user.id,Conversation.type == ConversationType.GROUP,)))).scalars().all()

    return [
        {
            "conversation_id": str(c.id),
            "name": c.name,
            "created_by": str(c.created_by) if c.created_by else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]

@router.post("/conversations/modify/addUser")
async def add_user_to_group(payload: AddUserToGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user), conversation_id: UUID = None):
    norm_grp_name = payload.group_name.lower()
    print("normalized group name:", norm_grp_name)
    group_id = (await db.execute(
        select(Conversation.id).where(
            and_(
                Conversation.name == norm_grp_name,
                Conversation.type == ConversationType.GROUP
            )
        )
    )).scalar_one_or_none()

    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    conversation = await db.get(Conversation, group_id)
    if not conversation or conversation.type != ConversationType.GROUP:
        raise HTTPException(status_code=404, detail="Group conversation not found")

    existing_member_ids = set((await db.execute(
        select(ConversationMember.user_id).where(ConversationMember.conversation_id == group_id)
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
    group_id = await _resolve_group_id(payload, db)
    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")
    
    if not payload.new_name or not payload.new_name.strip():
        raise HTTPException(status_code=400, detail="new_name is required")

    conversation_obj = (await db.execute(select(Conversation).where(Conversation.id==group_id))).scalar_one_or_none()
    old_group_name = conversation_obj.name
    conversation_obj.name = payload.new_name.strip()
    await db.commit()
    await db.refresh(conversation_obj)
    return {"conversation_id": conversation_obj.id, "type": "group","old_group_name": old_group_name, "new_group_name": conversation_obj.name, "created_by": auth_user.username, "admin": True}


@router.post("/conversations/modify/removeUser")
async def remove_user_from_group(payload: RemoveUserFromGroupRequest, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    if not payload.members_username or len(payload.members_username) == 0:
        raise HTTPException(status_code=400, detail="members_username is required")

    group_id = await _resolve_group_id(payload, db)

    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()


    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    if not payload.members_username:
        raise HTTPException(status_code=400, detail="members_username is required")

    target_ids = []
    target_names = []
    for username in payload.members_username:
        user, user_exists = await check_user_exists(username.strip(), db)
        if user_exists:
            target_ids.append(user.id)
            target_names.append(user.username)

    if not target_ids:
        raise HTTPException(status_code=404, detail="No valid users found")

    if auth_user.id in target_ids:
        raise HTTPException(status_code=400, detail="Admins cannot remove themselves; transfer admin or delete the group instead")

    targets = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id.in_(target_ids),
            )
        )
    )).scalars().all()

    if not targets:
        raise HTTPException(status_code=404, detail="The user to be deleted isn't in your group")

    for target in targets:
        await db.delete(target)
    await db.commit()
    return {"conversation_id": str(group_id), "removed_users": target_names}

@router.post("/conversation/getUsersInConversation")
async def get_all_group_users(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    if not payload.group_name:
        raise HTTPException(status_code=400, detail="group_name is required")
    group_id = await _resolve_group_id(payload, db)

    requester = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()
    if not requester:
        raise HTTPException(status_code=403, detail="You are not a member of this group")

    rows = (await db.execute(
        select(User, ConversationMember.is_user_admin, ConversationMember.joined_at)
        .join(ConversationMember, ConversationMember.user_id == User.id)
        .where(ConversationMember.conversation_id == group_id)
    )).all()

    return {
        "conversation_id": str(group_id),
        "group_name": payload.group_name.strip(),
        "members": [
            {
                "user_id": str(user.id),
                "username": user.username,
                "name": user.name,
                "cover_url": user.cover_url,
                "is_admin": is_admin,
                "joined_at": joined_at.isoformat() if joined_at else None,
            }
            for user, is_admin, joined_at in rows
        ],
    }


@router.post("/conversations/modify/makeAdmin")
async def make_another_user_admin(payload: GroupModify, db: AsyncSession = Depends(get_db), auth_user: dict = Depends(get_current_user)):
    if not payload.group_name:
        raise HTTPException(status_code=400, detail="group_name is required")

    group_id = await _resolve_group_id(payload, db)
    membership = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == auth_user.id,
            )
        )
    )).scalar_one_or_none()

    if not membership or not membership.is_user_admin:
        raise HTTPException(status_code=403, detail="User is not an admin of this group or group does not exist")

    data, user_exists = await check_user_exists(payload.target_username, db)
    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found")

    target = (await db.execute(
        select(ConversationMember).where(
            and_(
                ConversationMember.conversation_id == group_id,
                ConversationMember.user_id == data.id,
            )
        )
    )).scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="That user isn't in your group")

    target.is_user_admin = True
    await db.commit()
    return {"conversation_id": str(group_id), "user_name": str(data.name), "is_admin": True}
