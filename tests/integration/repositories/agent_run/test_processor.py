from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from promptune.agents.prompt_editor.schema import (
    EditorMessage,
    PromptEditorResponse,
    PromptProposalOutput,
)
from promptune.core.exceptions import ConflictError
from promptune.database.session import build_session_maker
from promptune.modules.agent_run.model import AgentRunStatus
from promptune.modules.agent_run.processor import AgentRunProcessor
from promptune.modules.agent_run.repository import AgentRunRepository
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import MessageRepository
from promptune.modules.message.schema import MessageSend
from promptune.modules.message.service import MessageService
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.repository import SessionRepository
from tests.integration.repositories._conversation import setup_conversation

pytestmark = pytest.mark.asyncio(loop_scope="session")


class FakePromptEditorAgent:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.failures = list(failures or [])
        self.calls: list[tuple[str | None, tuple[EditorMessage, ...], str]] = []

    async def respond(
        self,
        *,
        agent_context: str | None,
        messages: tuple[EditorMessage, ...],
        base_prompt_content: str,
    ) -> PromptEditorResponse:
        self.calls.append((agent_context, messages, base_prompt_content))
        if self.failures:
            raise self.failures.pop(0)
        return PromptEditorResponse(
            message="I prepared the requested revision.",
            questions=["Should the confirmation mention the date?"],
            warnings=["Review the scheduling policy."],
            proposal=PromptProposalOutput(
                proposed_content="# Revised prompt",
                proposed_description="Adds scheduling confirmation",
                summary=["Added a confirmation before scheduling"],
            ),
        )


async def enqueue_run(engine: AsyncEngine):
    maker = build_session_maker(engine)
    async with maker() as session:
        owner, _, agent, prompt, _ = await setup_conversation(session)
        conversation = await SessionRepository(session).create(
            user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
        )
        dispatch = await MessageService(
            MessageRepository(session),
            SessionRepository(session),
            AgentRunRepository(session),
        ).send_message(
            conversation.id,
            owner.id,
            MessageSend(content="  Add confirmation before scheduling  "),
        )
        await session.commit()
        return owner.id, conversation.id, dispatch.message.id, dispatch.run.id


async def test_processor_persists_assistant_proposal_and_completed_run(
    engine: AsyncEngine,
) -> None:
    owner_id, session_id, user_message_id, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    agent = FakePromptEditorAgent()
    processor = AgentRunProcessor(maker, agent, heartbeat_seconds=0)

    assert await processor.process_next()
    assert len(agent.calls) == 1
    context, messages, base_prompt = agent.calls[0]
    assert context == "Scheduling rules"
    assert base_prompt == "Base"
    assert [(item.role, item.content) for item in messages] == [
        ("user", "Add confirmation before scheduling")
    ]

    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        history = await MessageRepository(session).list_by_session(
            session_id, owner_id, 1, 10
        )
        proposal = (
            await session.execute(
                select(PromptProposal).where(
                    PromptProposal.message_id == run.assistant_message_id
                )
            )
        ).scalar_one()
    assert run is not None
    assert run.status == AgentRunStatus.COMPLETED
    assert run.attempt_count == 1
    assert run.finished_at is not None
    assert [message.role for message in history] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert history[1].reply_to_id == user_message_id
    assert history[1].questions == ["Should the confirmation mention the date?"]
    assert proposal.change_request == "Add confirmation before scheduling"
    assert proposal.proposed_content == "# Revised prompt"


async def test_processor_retries_only_transient_failure(engine: AsyncEngine) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    agent = FakePromptEditorAgent([TimeoutError("provider details")])
    processor = AgentRunProcessor(maker, agent, heartbeat_seconds=0, max_attempts=3)

    assert await processor.process_next()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run is not None
        assert run.status == AgentRunStatus.QUEUED
        assert run.error_code == "provider_unavailable"
        assert "provider details" not in run.error_message

    assert await processor.process_next()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run is not None
        assert run.status == AgentRunStatus.COMPLETED
        assert run.attempt_count == 2


async def test_processor_does_not_retry_permanent_failure(engine: AsyncEngine) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    processor = AgentRunProcessor(
        maker,
        FakePromptEditorAgent([ValueError("private provider payload")]),
        heartbeat_seconds=0,
    )

    assert await processor.process_next()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run is not None
        assert run.status == AgentRunStatus.FAILED
        assert run.attempt_count == 1
        assert run.error_code == "processing_failed"
        assert run.error_message == "The agent run could not be completed"


async def test_repository_recovers_expired_claim_and_enforces_one_active_run(
    engine: AsyncEngine,
) -> None:
    owner_id, session_id, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    now = datetime.now(UTC)
    async with maker() as session:
        repository = AgentRunRepository(session)
        claimed = await repository.claim_next(now=now, lease_seconds=1)
        assert claimed is not None and claimed.id == run_id
        claimed.lease_expires_at = now - timedelta(seconds=1)
        await session.commit()
    async with maker() as session:
        repository = AgentRunRepository(session)
        assert await repository.recover_expired(now=now, max_attempts=3) == 1
        await session.commit()
    async with maker() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run is not None and run.status == AgentRunStatus.QUEUED

    async with maker() as session:
        sessions = SessionRepository(session)
        with pytest.raises(ConflictError):
            await sessions.complete(session_id, owner_id)
        with pytest.raises(ConflictError):
            await sessions.delete(session_id, owner_id)
        service = MessageService(
            MessageRepository(session),
            SessionRepository(session),
            AgentRunRepository(session),
        )
        with pytest.raises(ConflictError):
            await service.send_message(
                session_id, owner_id, MessageSend(content="Concurrent request")
            )
        await session.rollback()
    async with maker() as session:
        count = (
            await session.execute(
                select(func.count(Message.id)).where(Message.session_id == session_id)
            )
        ).scalar_one()
        assert count == 1
