import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from promptune.agents.prompt_editor.schema import (
    EditorMessage,
    PromptEditorResponse,
    PromptProposalOutput,
)
from promptune.core.exceptions import ConflictError
from promptune.database.session import build_session_maker
from promptune.modules.agent_run.model import AgentRun, AgentRunStatus
from promptune.modules.agent_run.processor import AgentRunProcessor, ProcessResult
from promptune.modules.agent_run.repository import AgentRunRepository
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import MessageRepository
from promptune.modules.message.schema import MessageSend
from promptune.modules.message.service import MessageService
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session, SessionStatus
from promptune.modules.session.repository import SessionRepository
from tests.integration.repositories._conversation import setup_conversation
from tests.unit.agent_run.fake_publisher import FakeRunPublisher

pytestmark = pytest.mark.asyncio(loop_scope="session")


class FakePromptEditorAgent:
    def __init__(
        self, failures: list[Exception] | None = None, delay: float = 0
    ) -> None:
        self.failures = list(failures or [])
        self.delay = delay
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
        if self.delay:
            await asyncio.sleep(self.delay)
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


async def get_run(engine: AsyncEngine, owner_id, run_id) -> AgentRun:
    async with build_session_maker(engine)() as session:
        run = await AgentRunRepository(session).get_by_id(run_id, owner_id)
        assert run is not None
        return run


def make_processor(engine, agent, publisher=None, **kwargs) -> AgentRunProcessor:
    return AgentRunProcessor(
        build_session_maker(engine),
        agent,
        publisher or FakeRunPublisher(),
        **kwargs,
    )


async def test_processor_persists_assistant_proposal_and_completed_run(
    engine: AsyncEngine,
) -> None:
    owner_id, session_id, user_message_id, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    agent = FakePromptEditorAgent()

    assert await make_processor(engine, agent).process(run_id) == ProcessResult.ACK
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


async def test_processor_requeues_transient_failure_through_retry_queue(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    publisher = FakeRunPublisher()
    processor = make_processor(
        engine,
        FakePromptEditorAgent([TimeoutError("provider details")]),
        publisher,
        max_attempts=3,
    )

    assert await processor.process(run_id) == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.QUEUED
    assert run.error_code == "provider_unavailable"
    assert "provider details" not in run.error_message
    assert publisher.retried == [run_id]

    assert await processor.process(run_id) == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.COMPLETED
    assert run.attempt_count == 2
    assert run.error_code is None


async def test_processor_fails_transient_error_at_attempt_limit(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    publisher = FakeRunPublisher()
    processor = make_processor(
        engine,
        FakePromptEditorAgent([TimeoutError(), TimeoutError()]),
        publisher,
        max_attempts=2,
    )

    await processor.process(run_id)
    await processor.process(run_id)

    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.FAILED
    assert run.attempt_count == 2
    assert run.error_code == "provider_unavailable"
    assert publisher.retried == [run_id]


async def test_processor_does_not_retry_permanent_failure(engine: AsyncEngine) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    publisher = FakeRunPublisher()
    processor = make_processor(
        engine,
        FakePromptEditorAgent([ValueError("private provider payload")]),
        publisher,
    )

    assert await processor.process(run_id) == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.FAILED
    assert run.attempt_count == 1
    assert run.error_code == "processing_failed"
    assert run.error_message == "The agent run could not be completed"
    assert publisher.retried == []


async def test_processor_fails_run_when_retry_cannot_be_published(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    processor = make_processor(
        engine, FakePromptEditorAgent([TimeoutError()]), FakeRunPublisher(fail=True)
    )

    assert await processor.process(run_id) == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "queue_unavailable"


async def test_processor_treats_agent_timeout_as_transient(engine: AsyncEngine) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    publisher = FakeRunPublisher()
    processor = make_processor(
        engine, FakePromptEditorAgent(delay=5), publisher, timeout_seconds=0.05
    )

    assert await processor.process(run_id) == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.QUEUED
    assert run.error_code == "provider_unavailable"
    assert publisher.retried == [run_id]


async def test_processor_fails_run_that_exceeded_max_attempts(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    async with maker() as session:
        await session.execute(
            update(AgentRun).where(AgentRun.id == run_id).values(attempt_count=3)
        )
        await session.commit()
    agent = FakePromptEditorAgent()

    result = await make_processor(engine, agent, max_attempts=3).process(run_id)

    assert result == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "run_timeout"
    assert run.attempt_count == 4
    assert agent.calls == []


async def test_processor_takes_over_redelivered_processing_run(
    engine: AsyncEngine,
) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    async with maker() as session:
        claimed = await AgentRunRepository(session).claim_by_id(
            run_id, now=datetime.now(UTC)
        )
        assert claimed == 1
        await session.commit()

    result = await make_processor(engine, FakePromptEditorAgent()).process(run_id)

    assert result == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.COMPLETED
    assert run.attempt_count == 2


async def test_processor_acks_and_skips_terminal_run(engine: AsyncEngine) -> None:
    owner_id, _, _, run_id = await enqueue_run(engine)
    agent = FakePromptEditorAgent()
    processor = make_processor(engine, agent)
    await processor.process(run_id)

    assert await processor.process(run_id) == ProcessResult.ACK
    assert len(agent.calls) == 1
    assert (await get_run(engine, owner_id, run_id)).attempt_count == 1


@pytest.mark.parametrize(
    "change",
    [{"status": SessionStatus.COMPLETED}, {"deleted_at": datetime.now(UTC)}],
)
async def test_processor_skips_run_of_inactive_session(
    engine: AsyncEngine, change: dict
) -> None:
    _, session_id, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)
    async with maker() as session:
        await session.execute(
            update(Session).where(Session.id == session_id).values(**change)
        )
        await session.commit()
    agent = FakePromptEditorAgent()

    assert await make_processor(engine, agent).process(run_id) == ProcessResult.ACK

    assert agent.calls == []
    async with maker() as session:
        run = (
            await session.execute(select(AgentRun).where(AgentRun.id == run_id))
        ).scalar_one()
        assert run.status == AgentRunStatus.QUEUED
        assert run.attempt_count == 0


async def test_processor_discards_result_when_another_attempt_took_over(
    engine: AsyncEngine,
) -> None:
    owner_id, session_id, _, run_id = await enqueue_run(engine)
    maker = build_session_maker(engine)

    class TakeoverAgent(FakePromptEditorAgent):
        async def respond(self, **kwargs):
            async with maker() as session:
                await AgentRunRepository(session).claim_by_id(
                    run_id, now=datetime.now(UTC)
                )
                await session.commit()
            return await super().respond(**kwargs)

    result = await make_processor(engine, TakeoverAgent()).process(run_id)

    assert result == ProcessResult.ACK
    run = await get_run(engine, owner_id, run_id)
    assert run.status == AgentRunStatus.PROCESSING
    assert run.attempt_count == 2
    assert run.assistant_message_id is None
    async with maker() as session:
        count = (
            await session.execute(
                select(func.count(Message.id)).where(Message.session_id == session_id)
            )
        ).scalar_one()
    assert count == 1


async def test_processor_requeues_message_on_database_failure() -> None:
    def broken_maker():
        raise OperationalError("SELECT 1", {}, Exception("database down"))

    processor = AgentRunProcessor(
        broken_maker, FakePromptEditorAgent(), FakeRunPublisher()
    )

    assert await processor.process(uuid4()) == ProcessResult.NACK_REQUEUE


async def test_active_run_blocks_complete_delete_and_new_message(
    engine: AsyncEngine,
) -> None:
    owner_id, session_id, _, _ = await enqueue_run(engine)
    maker = build_session_maker(engine)
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
