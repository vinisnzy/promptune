from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.agents.prompt_editor.context import prepare_editor_context
from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.message.model import Message, MessageRole
from promptune.modules.message.repository import MessageRepository
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session
from promptune.modules.session.repository import SessionRepository
from tests.integration.repositories._conversation import setup_conversation

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_message_history_and_editor_bases(session: AsyncSession):
    owner, _, agent, prompt, _ = await setup_conversation(session)
    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    conversation = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    initial = await messages.create(
        session_id=conversation.id, role=MessageRole.USER, content="Edit"
    )
    loaded_session = await sessions.get_by_id(conversation.id, owner.id)
    loaded_initial = await messages.get_by_id(initial.id, conversation.id)
    assert loaded_session is not None and loaded_initial is not None
    assert prepare_editor_context(loaded_session, loaded_initial, []).base_prompt_content == "Base"

    assistant = await messages.create(
        session_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="Suggested change",
        reply_to_id=initial.id,
        questions=["Clarify?"],
    )
    initial.created_at = datetime.now(UTC) - timedelta(seconds=2)
    assistant.created_at = initial.created_at + timedelta(seconds=1)
    await session.flush()
    proposal = PromptProposal(
        agent_id=agent.id,
        source_prompt_id=prompt.id,
        message_id=assistant.id,
        change_request="Edit",
        proposed_content="Proposal one",
        proposed_description="Updated",
        summary=["Changed"],
        questions=[],
        warnings=[],
        status="pending",
    )
    session.add(proposal)
    await session.flush()
    current = await messages.create(
        session_id=conversation.id,
        role=MessageRole.USER,
        content="Revise again",
        base_proposal_id=proposal.id,
    )
    current.created_at = assistant.created_at + timedelta(seconds=1)
    await session.flush()
    loaded_current = await messages.get_by_id(current.id, conversation.id)
    history = await messages.list_before_for_editing(conversation.id, current.id)
    assert loaded_current is not None
    assert loaded_current.base_proposal is proposal
    assert loaded_current.base_proposal.message is assistant
    assert [item.id for item in history] == [initial.id, assistant.id]
    assert history[-1].proposal is proposal
    assert prepare_editor_context(
        loaded_session, loaded_current, history
    ).base_prompt_content == "Proposal one"
    assert await messages.list_by_session(conversation.id, 1, 2) == history
    assert [item.id for item in await messages.list_by_session(conversation.id, 2, 2)] == [
        current.id
    ]

    follow_up = await messages.create(
        session_id=conversation.id, role=MessageRole.USER, content="Continue"
    )
    follow_up.created_at = current.created_at + timedelta(seconds=1)
    await session.flush()
    fallback_history = await messages.list_before_for_editing(conversation.id, follow_up.id)
    assert prepare_editor_context(
        loaded_session, follow_up, fallback_history
    ).base_prompt_content == "Proposal one"


async def test_message_references_status_and_isolation(session: AsyncSession):
    owner, _, agent, prompt, _ = await setup_conversation(session)
    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    first = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    second = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    other_message = await messages.create(
        session_id=second.id, role=MessageRole.USER, content="Other"
    )
    other_proposal = PromptProposal(
        agent_id=agent.id,
        source_prompt_id=prompt.id,
        message_id=other_message.id,
        change_request="Other",
        proposed_content="Other proposal",
        proposed_description="Other",
        summary=[],
        questions=[],
        warnings=[],
        status="pending",
    )
    session.add(other_proposal)
    await session.flush()
    assert await messages.get_by_id(other_message.id, first.id) is None
    assert await messages.list_by_session(first.id, 1, 10) == []
    with pytest.raises(InvalidInputError):
        await messages.create(
            session_id=first.id,
            role=MessageRole.USER,
            content="Reply",
            reply_to_id=other_message.id,
        )
    with pytest.raises(InvalidInputError):
        await messages.create(
            session_id=first.id,
            role="invalid",
            content="Bad role",
        )
    with pytest.raises(InvalidInputError):
        await messages.create(
            session_id=first.id,
            role=MessageRole.USER,
            content="Bad proposal",
            base_proposal_id=other_proposal.id,
        )
    with pytest.raises(NotFoundError):
        await messages.list_before_for_editing(first.id, other_message.id)
    with pytest.raises(InvalidInputError):
        await messages.list_by_session(first.id, 1, 0)
    await sessions.complete(first.id, owner.id)
    with pytest.raises(ConflictError):
        await messages.create(
            session_id=first.id, role=MessageRole.USER, content="Too late"
        )


async def test_message_creation_leaves_transaction_open(session: AsyncSession):
    owner, _, agent, prompt, _ = await setup_conversation(session)
    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    conversation = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    message = await messages.create(
        session_id=conversation.id, role=MessageRole.USER, content="Transient"
    )
    await session.rollback()
    assert (
        await session.execute(select(Session).where(Session.id == conversation.id))
    ).scalar_one_or_none() is None
    assert (
        await session.execute(select(Message).where(Message.id == message.id))
    ).scalar_one_or_none() is None


async def test_message_timestamp_ties_and_deleted_agent_visibility(
    session: AsyncSession,
):
    owner, _, agent, prompt, _ = await setup_conversation(session)
    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    conversation = await sessions.create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    first = await messages.create(
        session_id=conversation.id, role=MessageRole.USER, content="First"
    )
    second = await messages.create(
        session_id=conversation.id, role=MessageRole.USER, content="Second"
    )
    tied_time = datetime.now(UTC)
    first.created_at = tied_time
    second.created_at = tied_time
    await session.flush()
    ordered = await messages.list_by_session(conversation.id, 1, 10)
    assert [item.id for item in ordered] == sorted([first.id, second.id])
    assert [
        item.id
        for item in await messages.list_before_for_editing(
            conversation.id, max(first.id, second.id)
        )
    ] == [min(first.id, second.id)]

    agent.deleted_at = datetime.now(UTC)
    await session.flush()
    assert await messages.get_by_id(first.id, conversation.id) is None
    assert await messages.list_by_session(conversation.id, 1, 10) == []
    with pytest.raises(InvalidInputError):
        await messages.create(
            session_id=conversation.id, role=MessageRole.USER, content="Hidden"
        )
