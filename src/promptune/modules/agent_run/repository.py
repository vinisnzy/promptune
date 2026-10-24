from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent.model import Agent
from promptune.modules.agent_run.model import AgentRun, AgentRunStatus
from promptune.modules.agent_run.notification import notify_agent_run_changed
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session, SessionStatus


class IAgentRunRepository(ABC):
    @abstractmethod
    async def create(self, *, session_id: UUID, user_message_id: UUID) -> AgentRun: ...

    @abstractmethod
    async def get_by_id(self, run_id: UUID, user_id: UUID) -> AgentRun | None: ...

    @abstractmethod
    async def has_active_for_session(self, session_id: UUID) -> bool: ...

    @abstractmethod
    async def claim_by_id(self, run_id: UUID, *, now: datetime) -> int | None: ...

    @abstractmethod
    async def get_for_processing(self, run_id: UUID) -> AgentRun | None: ...

    @abstractmethod
    async def mark_completed(
        self,
        run_id: UUID,
        attempt_count: int,
        assistant_message_id: UUID,
        *,
        now: datetime,
    ) -> bool: ...

    @abstractmethod
    async def mark_error(
        self,
        run_id: UUID,
        attempt_count: int,
        *,
        code: str,
        message: str,
        retry: bool,
        now: datetime,
    ) -> bool: ...

    @abstractmethod
    async def mark_failed(
        self, run_id: UUID, *, code: str, message: str, now: datetime
    ) -> bool: ...


class AgentRunRepository(IAgentRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, session_id: UUID, user_message_id: UUID) -> AgentRun:
        message_stmt = select(Message.id).where(
            Message.id == user_message_id,
            Message.session_id == session_id,
            Message.role == MessageRole.USER,
        )
        if (await self.session.execute(message_stmt)).scalar_one_or_none() is None:
            raise InvalidInputError("Agent run requires a user message from its session")
        run = AgentRun(
            session_id=session_id,
            user_message_id=user_message_id,
            status=AgentRunStatus.QUEUED,
            attempt_count=0,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: UUID, user_id: UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .join(Session, AgentRun.session_id == Session.id)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                AgentRun.id == run_id,
                Session.user_id == user_id,
                Session.deleted_at.is_(None),
                Agent.deleted_at.is_(None),
            )
            .options(
                selectinload(AgentRun.assistant_message).selectinload(Message.proposal)
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def has_active_for_session(self, session_id: UUID) -> bool:
        stmt = select(AgentRun.id).where(
            AgentRun.session_id == session_id,
            AgentRun.status.in_((AgentRunStatus.QUEUED, AgentRunStatus.PROCESSING)),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def claim_by_id(self, run_id: UUID, *, now: datetime) -> int | None:
        """Atomically start an attempt; returns the new attempt_count or None."""
        runnable_session = (
            select(Session.id)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                Session.id == AgentRun.session_id,
                Session.status == SessionStatus.ACTIVE,
                Session.deleted_at.is_(None),
                Agent.deleted_at.is_(None),
            )
        )
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status.in_(
                    (AgentRunStatus.QUEUED, AgentRunStatus.PROCESSING)
                ),
                exists(runnable_session),
            )
            .values(
                status=AgentRunStatus.PROCESSING,
                attempt_count=AgentRun.attempt_count + 1,
                started_at=func.coalesce(AgentRun.started_at, now),
                finished_at=None,
                error_code=None,
                error_message=None,
            )
            .returning(AgentRun.attempt_count)
            .execution_options(synchronize_session=False)
        )
        attempt_count = (await self.session.execute(stmt)).scalar_one_or_none()
        if attempt_count is not None:
            await notify_agent_run_changed(self.session, run_id)
        return attempt_count

    async def get_for_processing(self, run_id: UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(
                selectinload(AgentRun.session).selectinload(Session.agent),
                selectinload(AgentRun.session).selectinload(Session.base_prompt),
                selectinload(AgentRun.user_message)
                .selectinload(Message.base_proposal)
                .selectinload(PromptProposal.message),
            )
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def mark_completed(
        self,
        run_id: UUID,
        attempt_count: int,
        assistant_message_id: UUID,
        *,
        now: datetime,
    ) -> bool:
        return await self._finish_attempt(
            run_id,
            attempt_count,
            assistant_message_id=assistant_message_id,
            status=AgentRunStatus.COMPLETED,
            error_code=None,
            error_message=None,
            finished_at=now,
        )

    async def mark_error(
        self,
        run_id: UUID,
        attempt_count: int,
        *,
        code: str,
        message: str,
        retry: bool,
        now: datetime,
    ) -> bool:
        return await self._finish_attempt(
            run_id,
            attempt_count,
            status=AgentRunStatus.QUEUED if retry else AgentRunStatus.FAILED,
            error_code=code,
            error_message=message,
            finished_at=None if retry else now,
        )

    async def mark_failed(
        self, run_id: UUID, *, code: str, message: str, now: datetime
    ) -> bool:
        """Fail a run regardless of its attempt; for runs with no live attempt."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status.in_(
                    (AgentRunStatus.QUEUED, AgentRunStatus.PROCESSING)
                ),
            )
            .values(
                status=AgentRunStatus.FAILED,
                error_code=code,
                error_message=message,
                finished_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return await self._execute_transition(stmt, run_id)

    async def _finish_attempt(
        self, run_id: UUID, attempt_count: int, **values: object
    ) -> bool:
        # Fencing: only the attempt that currently owns the run may change it.
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.PROCESSING,
                AgentRun.attempt_count == attempt_count,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return await self._execute_transition(stmt, run_id)

    async def _execute_transition(self, stmt, run_id: UUID) -> bool:
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            return False
        await notify_agent_run_changed(self.session, run_id)
        return True
