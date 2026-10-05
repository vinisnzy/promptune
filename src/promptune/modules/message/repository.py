from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.agent.model import Agent
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session, SessionStatus


def _check_page(page: int, size: int) -> None:
    if page < 1 or size < 1:
        raise InvalidInputError("page and size must be positive")


class IMessageRepository(ABC):
    @abstractmethod
    async def create(
        self,
        *,
        session_id: UUID,
        role: MessageRole,
        content: str,
        reply_to_id: UUID | None = None,
        base_proposal_id: UUID | None = None,
        questions: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Message: ...

    @abstractmethod
    async def get_by_id(self, message_id: UUID, session_id: UUID) -> Message | None: ...

    @abstractmethod
    async def list_by_session(
        self, session_id: UUID, page: int, size: int
    ) -> Sequence[Message]: ...

    @abstractmethod
    async def list_before_for_editing(
        self, session_id: UUID, message_id: UUID
    ) -> Sequence[Message]: ...


class MessageRepository(IMessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _visible_session(self, session_id: UUID):
        return (
            select(Session)
            .join(Agent, Session.agent_id == Agent.id)
            .where(Session.id == session_id, Agent.deleted_at.is_(None))
        )

    async def create(
        self,
        *,
        session_id: UUID,
        role: MessageRole,
        content: str,
        reply_to_id: UUID | None = None,
        base_proposal_id: UUID | None = None,
        questions: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Message:
        if role not in (MessageRole.USER, MessageRole.ASSISTANT):
            raise InvalidInputError("Invalid message role")
        conversation = (
            await self.session.execute(
                self._visible_session(session_id).with_for_update(of=Session)
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise InvalidInputError("Session does not exist")
        if conversation.status != SessionStatus.ACTIVE:
            raise ConflictError("Session is completed")
        if reply_to_id is not None:
            reply_stmt = select(Message.id).where(
                Message.id == reply_to_id, Message.session_id == session_id
            )
            if (await self.session.execute(reply_stmt)).scalar_one_or_none() is None:
                raise InvalidInputError("Reply target must belong to this session")
        if base_proposal_id is not None:
            proposal_stmt = (
                select(PromptProposal.id)
                .join(Message, PromptProposal.message_id == Message.id)
                .where(
                    PromptProposal.id == base_proposal_id,
                    Message.session_id == session_id,
                )
            )
            if (await self.session.execute(proposal_stmt)).scalar_one_or_none() is None:
                raise InvalidInputError("Base proposal must belong to this session")
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            reply_to_id=reply_to_id,
            base_proposal_id=base_proposal_id,
            questions=list(questions or []),
            warnings=list(warnings or []),
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get_by_id(self, message_id: UUID, session_id: UUID) -> Message | None:
        stmt = (
            select(Message)
            .where(Message.id == message_id, Message.session_id == session_id)
            .where(self._visible_session(session_id).exists())
            .options(
                selectinload(Message.base_proposal).selectinload(PromptProposal.message)
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_session(
        self, session_id: UUID, page: int, size: int
    ) -> Sequence[Message]:
        _check_page(page, size)
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .where(self._visible_session(session_id).exists())
            .order_by(Message.created_at, Message.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def list_before_for_editing(
        self, session_id: UUID, message_id: UUID
    ) -> Sequence[Message]:
        current = await self.get_by_id(message_id, session_id)
        if current is None:
            raise NotFoundError("Message does not exist in this session")
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                or_(
                    Message.created_at < current.created_at,
                    and_(
                        Message.created_at == current.created_at,
                        Message.id < current.id,
                    ),
                ),
            )
            .options(selectinload(Message.proposal))
            .order_by(Message.created_at, Message.id)
        )
        return (await self.session.execute(stmt)).scalars().all()
