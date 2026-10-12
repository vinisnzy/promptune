from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent.model import Agent
from promptune.modules.agent_run.model import AgentRun, AgentRunStatus
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

    async def recover_expired(self, *, now: datetime, max_attempts: int) -> int:
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.status == AgentRunStatus.PROCESSING,
                AgentRun.lease_expires_at.is_not(None),
                AgentRun.lease_expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        expired = (await self.session.execute(stmt)).scalars().all()
        for run in expired:
            run.lease_token = None
            run.lease_expires_at = None
            if run.attempt_count < max_attempts:
                run.status = AgentRunStatus.QUEUED
                run.error_code = "worker_timeout"
                run.error_message = "The worker stopped before completing the run"
            else:
                run.status = AgentRunStatus.FAILED
                run.error_code = "run_timeout"
                run.error_message = "The run exceeded the retry limit"
                run.finished_at = now
        if expired:
            await self.session.flush()
        return len(expired)

    async def claim_next(self, *, now: datetime, lease_seconds: int) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .join(Session, AgentRun.session_id == Session.id)
            .join(Agent, Session.agent_id == Agent.id)
            .where(
                AgentRun.status == AgentRunStatus.QUEUED,
                Session.status == SessionStatus.ACTIVE,
                Session.deleted_at.is_(None),
                Agent.deleted_at.is_(None),
            )
            .order_by(AgentRun.created_at, AgentRun.id)
            .with_for_update(of=AgentRun, skip_locked=True)
            .limit(1)
        )
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None
        run.status = AgentRunStatus.PROCESSING
        run.attempt_count += 1
        run.started_at = run.started_at or now
        run.finished_at = None
        run.error_code = None
        run.error_message = None
        run.lease_token = uuid4()
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        await self.session.flush()
        return run

    async def get_claimed(self, run_id: UUID, lease_token: UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.PROCESSING,
                AgentRun.lease_token == lease_token,
            )
            .options(
                selectinload(AgentRun.session).selectinload(Session.agent),
                selectinload(AgentRun.session).selectinload(Session.base_prompt),
                selectinload(AgentRun.user_message)
                .selectinload(Message.base_proposal)
                .selectinload(PromptProposal.message),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def lock_claimed(self, run_id: UUID, lease_token: UUID) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == AgentRunStatus.PROCESSING,
                AgentRun.lease_token == lease_token,
            )
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def heartbeat(
        self, run_id: UUID, lease_token: UUID, *, now: datetime, lease_seconds: int
    ) -> bool:
        run = await self.lock_claimed(run_id, lease_token)
        if run is None:
            return False
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        await self.session.flush()
        return True

    async def mark_completed(
        self, run: AgentRun, assistant_message_id: UUID, *, now: datetime
    ) -> None:
        run.assistant_message_id = assistant_message_id
        run.status = AgentRunStatus.COMPLETED
        run.error_code = None
        run.error_message = None
        run.finished_at = now
        run.lease_token = None
        run.lease_expires_at = None
        await self.session.flush()

    async def mark_error(
        self,
        run: AgentRun,
        *,
        code: str,
        message: str,
        retry: bool,
        now: datetime,
    ) -> None:
        run.error_code = code
        run.error_message = message
        run.lease_token = None
        run.lease_expires_at = None
        if retry:
            run.status = AgentRunStatus.QUEUED
        else:
            run.status = AgentRunStatus.FAILED
            run.finished_at = now
        await self.session.flush()
