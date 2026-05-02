"""
Group chat routes — HTTP CRUD + per-user and per-thread WebSocket endpoints.
"""
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.group_chat import GroupChatMember
from app.models.user import User
from app.schemas.group_chat import (
    GroupChatOut,
    GroupMessageOut,
    InviteIn,
    InviteOut,
    MemberOut,
    ReadReceiptIn,
    SendMessageIn,
    ThreadListItem,
    UserSummary,
)
from app.services import group_chat_service as svc
from app.realtime.events import (
    AgentTypingEvent,
    InviteAcceptedEvent,
    InviteCancelledEvent,
    InviteNewEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
    MessageNewEvent,
    PresenceEvent,
    ReadReceiptEvent,
    ThreadUnreadBumpEvent,
    TypingEvent,
)
from app.utils.jwt_handler import verify_access_token

router = APIRouter(prefix="/group-chat", tags=["Group Chat"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg_to_dict(msg) -> dict:
    """Serialize a GroupChatMessage to a plain dict for events."""
    return GroupMessageOut.model_validate(msg).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Eligible invitees
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/eligible-invitees", response_model=list[UserSummary])
async def get_eligible_invitees(
    file_id: int,
    group_chat_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = await svc.list_eligible(db, file_id, current_user.id, group_chat_id)
    return [UserSummary.model_validate(u) for u in users]


# ---------------------------------------------------------------------------
# Send invites
# ---------------------------------------------------------------------------


@router.post("/files/{file_id}/invite", status_code=status.HTTP_201_CREATED)
async def send_invites(
    file_id: int,
    body: InviteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gc, invites = await svc.send_invites(
        db, file_id, current_user, body.user_ids, body.group_chat_id
    )
    await db.commit()

    # Notify each invitee via their user-level WebSocket
    cm = request.app.state.connection_manager
    for inv in invites:
        event = InviteNewEvent(invite=InviteOut.model_validate(inv).model_dump(mode="json"))
        await cm.send_to_user(inv.invitee_id, event)

    return {
        "group_chat_id": gc.id,
        "invites": [InviteOut.model_validate(i).model_dump(mode="json") for i in invites],
    }


# ---------------------------------------------------------------------------
# Invite responses
# ---------------------------------------------------------------------------


@router.get("/invites/pending", response_model=list[InviteOut])
async def get_pending_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invites = await svc.get_pending_invites(db, current_user.id)
    return [InviteOut.model_validate(i) for i in invites]


@router.post("/invites/{invite_id}/accept", response_model=GroupChatOut)
async def accept_invite(
    invite_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gc = await svc.accept_invite(db, invite_id, current_user)
    await db.commit()

    # Notify all members of the thread
    cm = request.app.state.connection_manager
    event = InviteAcceptedEvent(
        invite_id=invite_id,
        group_chat_id=gc.id,
        user_id=current_user.id,
    )
    for member in gc.members:
        if member.user_id != current_user.id:
            await cm.send_to_user(member.user_id, event)

    return GroupChatOut.model_validate(gc)


@router.post("/invites/{invite_id}/reject")
async def reject_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite = await svc.reject_invite(db, invite_id, current_user)
    await db.commit()
    return InviteOut.model_validate(invite)


@router.post("/invites/{invite_id}/cancel")
async def cancel_invite(
    invite_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite = await svc.cancel_invite(db, invite_id, current_user)
    await db.commit()

    # Notify invitee
    cm = request.app.state.connection_manager
    event = InviteCancelledEvent(
        invite_id=invite_id,
        group_chat_id=invite.group_chat_id,
    )
    await cm.send_to_user(invite.invitee_id, event)

    return InviteOut.model_validate(invite)


# ---------------------------------------------------------------------------
# Thread management
# ---------------------------------------------------------------------------


@router.get("/threads", response_model=list[ThreadListItem])
async def list_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    threads = await svc.list_threads_for_user(db, current_user.id)
    return [ThreadListItem(**t) for t in threads]


@router.get("/threads/{group_chat_id}", response_model=GroupChatOut)
async def get_thread(
    group_chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gc = await svc.get_thread(db, group_chat_id, current_user.id)
    return GroupChatOut.model_validate(gc)


@router.post("/threads/{group_chat_id}/leave")
async def leave_thread(
    group_chat_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await svc.leave_thread(db, group_chat_id, current_user.id)
    await db.commit()

    cm = request.app.state.connection_manager
    event = MemberLeftEvent(thread_id=group_chat_id, user_id=current_user.id)
    await cm.broadcast_thread(group_chat_id, event)

    return {"detail": "Left the group chat"}


@router.post("/threads/{group_chat_id}/read")
async def mark_read(
    group_chat_id: int,
    body: ReadReceiptIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await svc.update_read_seq(db, group_chat_id, current_user.id, body.last_seq)
    await db.commit()

    cm = request.app.state.connection_manager
    event = ReadReceiptEvent(
        thread_id=group_chat_id,
        user_id=current_user.id,
        last_seq=body.last_seq,
    )
    await cm.broadcast_thread(group_chat_id, event)

    return {"detail": "Read receipt updated"}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.post("/threads/{group_chat_id}/messages", response_model=GroupMessageOut)
async def send_message(
    group_chat_id: int,
    body: SendMessageIn,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify membership
    await svc.get_thread(db, group_chat_id, current_user.id)

    # Rate limit check
    redis = getattr(request.app.state, "redis", None)
    from app.realtime.rate_limit import check_message_rate
    if not await check_message_rate(current_user.id, group_chat_id, redis):
        raise HTTPException(
            status_code=429,
            detail="Message rate limit exceeded: max 10 messages per 10 seconds",
        )

    # Send message
    msg = await svc.send_message(
        db,
        thread_id=group_chat_id,
        user_id=current_user.id,
        content=body.content,
        reply_to_id=body.reply_to_id,
        client_msg_id=body.client_msg_id,
    )

    # Broadcast to thread
    cm = request.app.state.connection_manager
    event = MessageNewEvent(message=_msg_to_dict(msg))
    await cm.broadcast_thread(group_chat_id, event)

    # Notify ONLY @-mentioned users (not all thread members) — bell counter
    # should reflect "you were tagged", not "any chat happened".
    online_in_thread = set(cm.presence_for_thread(group_chat_id))
    mentioned_user_ids: set[int] = set()
    for m in (msg.mentions or []):
        if m.get("kind") == "user":
            uid = m.get("user_id")
            if isinstance(uid, int):
                mentioned_user_ids.add(uid)

    if mentioned_user_ids:
        _bump_event = ThreadUnreadBumpEvent(thread_id=group_chat_id, unread_count=1)
        for _uid in mentioned_user_ids:
            if _uid != current_user.id and _uid not in online_in_thread:
                await cm.send_to_user(_uid, _bump_event)

    # Queue agent ONLY when @SAMpai is mentioned. There is no off-topic guard
    # on regular messages — students chat freely; SAMpai is silent until called.
    agent = getattr(request.app.state, "group_chat_agent", None)
    has_agent_mention = any(m.get("kind") == "agent" for m in (msg.mentions or []))

    if agent is not None and has_agent_mention:
        from app.models.group_chat import GroupChat
        gc_q = await db.execute(
            select(GroupChat).where(GroupChat.id == group_chat_id)
        )
        gc = gc_q.scalar_one()

        from app.realtime.rate_limit import check_agent_rate
        if not await check_agent_rate(current_user.id, group_chat_id, redis):
            await svc.send_message(
                db,
                thread_id=group_chat_id,
                user_id=None,
                content="@SAMpai rate limit reached. Please wait before mentioning again.",
                role=__import__("app.models.group_chat", fromlist=["GroupMessageRole"]).GroupMessageRole.SYSTEM,
            )
            await db.commit()
        else:
            background_tasks.add_task(
                agent.run_respond, msg.id, group_chat_id, gc.file_id
            )

    return GroupMessageOut.model_validate(msg)


@router.get("/threads/{group_chat_id}/messages", response_model=list[GroupMessageOut])
async def get_messages(
    group_chat_id: int,
    before_seq: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await svc.get_thread(db, group_chat_id, current_user.id)
    messages = await svc.list_messages(db, group_chat_id, before_seq, limit)
    return [GroupMessageOut.model_validate(m) for m in messages]


# ---------------------------------------------------------------------------
# User-level WebSocket (for invites and user-scoped events)
# ---------------------------------------------------------------------------


@router.websocket("/ws/user")
async def ws_user(
    websocket: WebSocket,
    token: str = Query(...),
):
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=4401)
        return

    user_id = int(payload.get("sub"))
    cm = websocket.app.state.connection_manager

    await websocket.accept()
    await cm.register_user(websocket, user_id)
    logger.info(f"[ws/user] user_id={user_id} connected")

    try:
        while True:
            # Keep-alive — ignore incoming text
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"[ws/user] user_id={user_id} disconnected")
    finally:
        await cm.disconnect(websocket)


# ---------------------------------------------------------------------------
# Per-thread WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/group-chat/{group_chat_id}")
async def ws_thread(
    websocket: WebSocket,
    group_chat_id: int,
    token: str = Query(...),
):
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=4401)
        return

    user_id = int(payload.get("sub"))
    cm = websocket.app.state.connection_manager

    # Verify membership (need DB session for this)
    from app.database.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(GroupChatMember).where(
                    GroupChatMember.group_chat_id == group_chat_id,
                    GroupChatMember.user_id == user_id,
                )
            )
            member = result.scalar_one_or_none()
            if member is None:
                await websocket.close(code=4403)
                return
            result2 = await db.execute(select(User).where(User.id == user_id))
            current_user = result2.scalar_one_or_none()
        except Exception as exc:
            logger.error(f"[ws/thread] auth error: {exc}")
            await websocket.close(code=4500)
            return

    await websocket.accept()
    await cm.register_thread(websocket, group_chat_id, user_id)
    logger.info(f"[ws/thread] thread={group_chat_id} user={user_id} connected")

    # Send initial presence snapshot
    online_ids = cm.presence_for_thread(group_chat_id)
    presence_event = PresenceEvent(thread_id=group_chat_id, online_user_ids=online_ids)
    await websocket.send_text(presence_event.model_dump_json())

    # Broadcast member_joined to other members
    joined_event = MemberJoinedEvent(
        thread_id=group_chat_id,
        user_id=user_id,
        username=current_user.username if current_user else str(user_id),
    )
    await cm.broadcast_thread(group_chat_id, joined_event, exclude=websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "typing":
                event = TypingEvent(
                    thread_id=group_chat_id,
                    user_id=user_id,
                    username=current_user.username if current_user else str(user_id),
                    is_typing=data.get("is_typing", True),
                )
                await cm.broadcast_thread(group_chat_id, event, exclude=websocket)

            elif msg_type == "read_receipt":
                last_seq = data.get("last_seq")
                if last_seq is not None:
                    async with AsyncSessionLocal() as db:
                        await svc.update_read_seq(db, group_chat_id, user_id, int(last_seq))
                        await db.commit()
                    event = ReadReceiptEvent(
                        thread_id=group_chat_id,
                        user_id=user_id,
                        last_seq=int(last_seq),
                    )
                    await cm.broadcast_thread(group_chat_id, event, exclude=websocket)

    except WebSocketDisconnect:
        logger.info(f"[ws/thread] thread={group_chat_id} user={user_id} disconnected")
    finally:
        await cm.disconnect(websocket)
        # Broadcast updated presence
        updated_ids = cm.presence_for_thread(group_chat_id)
        presence_out = PresenceEvent(
            thread_id=group_chat_id, online_user_ids=updated_ids
        )
        await cm.broadcast_thread(group_chat_id, presence_out)
        # Broadcast member_left
        left_event = MemberLeftEvent(thread_id=group_chat_id, user_id=user_id)
        await cm.broadcast_thread(group_chat_id, left_event)
