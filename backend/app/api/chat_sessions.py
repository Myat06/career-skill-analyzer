import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.deps import SessionDep, get_student_or_404
from app.models import ChatSession, JobRole
from app.schemas import ChatSessionOut, ChatSessionPinIn, ChatSessionSaveIn, ChatSessionSummaryOut

router = APIRouter(tags=["chat-sessions"])

TITLE_MAX_LENGTH = 60


def _derive_title(display_messages: list[dict]) -> str | None:
    """First user message, truncated -- the same "name it after what was
    first said" convention chat UIs generally use, so a saved session reads
    as something recognizable in the history list rather than a bare
    timestamp."""
    for message in display_messages:
        if message.get("role") == "user":
            text = (message.get("content") or "").strip()
            if not text:
                continue
            return text if len(text) <= TITLE_MAX_LENGTH else text[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return None


async def _get_session_or_404(student_id: uuid.UUID, session_id: uuid.UUID, session: SessionDep) -> ChatSession:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None or chat_session.student_id != student_id:
        raise HTTPException(status_code=404, detail=f"Chat session {session_id} not found for this student")
    return chat_session


async def _to_out(chat_session: ChatSession, session: SessionDep) -> ChatSessionOut:
    job_role = await session.get(JobRole, chat_session.job_role_id) if chat_session.job_role_id else None
    return ChatSessionOut(
        id=chat_session.id,
        title=chat_session.title,
        job_role_id=chat_session.job_role_id,
        pinned=chat_session.pinned,
        updated_at=chat_session.updated_at,
        display_messages=chat_session.display_messages,
        chat_history=chat_session.chat_history,
        job_role=job_role,
    )


@router.get("/students/{student_id}/chat-sessions", response_model=list[ChatSessionSummaryOut])
async def list_chat_sessions(student_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    sessions = (
        await session.execute(
            select(ChatSession)
            .where(ChatSession.student_id == student_id)
            .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
        )
    ).scalars().all()
    return sessions


@router.get("/students/{student_id}/chat-sessions/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(student_id: uuid.UUID, session_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    chat_session = await _get_session_or_404(student_id, session_id, session)
    return await _to_out(chat_session, session)


@router.post("/students/{student_id}/chat-sessions", response_model=ChatSessionOut, status_code=201)
async def create_chat_session(student_id: uuid.UUID, payload: ChatSessionSaveIn, session: SessionDep):
    await get_student_or_404(student_id, session)
    chat_session = ChatSession(
        student_id=student_id,
        job_role_id=payload.job_role_id,
        title=_derive_title(payload.display_messages),
        display_messages=payload.display_messages,
        chat_history=payload.chat_history,
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return await _to_out(chat_session, session)


@router.patch("/students/{student_id}/chat-sessions/{session_id}", response_model=ChatSessionOut)
async def update_chat_session(student_id: uuid.UUID, session_id: uuid.UUID, payload: ChatSessionSaveIn, session: SessionDep):
    await get_student_or_404(student_id, session)
    chat_session = await _get_session_or_404(student_id, session_id, session)
    chat_session.display_messages = payload.display_messages
    chat_session.chat_history = payload.chat_history
    chat_session.job_role_id = payload.job_role_id
    # A title, once set, never changes retroactively -- only fill it in if this
    # session somehow still doesn't have one (e.g. its first save had no user
    # message yet, an edge case rather than the normal path).
    if not chat_session.title:
        chat_session.title = _derive_title(payload.display_messages)
    await session.commit()
    await session.refresh(chat_session)
    return await _to_out(chat_session, session)


@router.patch("/students/{student_id}/chat-sessions/{session_id}/pin", response_model=ChatSessionOut)
async def set_chat_session_pinned(student_id: uuid.UUID, session_id: uuid.UUID, payload: ChatSessionPinIn, session: SessionDep):
    await get_student_or_404(student_id, session)
    chat_session = await _get_session_or_404(student_id, session_id, session)
    chat_session.pinned = payload.pinned
    await session.commit()
    await session.refresh(chat_session)
    return await _to_out(chat_session, session)


@router.delete("/students/{student_id}/chat-sessions/{session_id}", status_code=204)
async def delete_chat_session(student_id: uuid.UUID, session_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    chat_session = await _get_session_or_404(student_id, session_id, session)
    await session.delete(chat_session)
    await session.commit()
