from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from promptune.agents.prompt_editor.context import prepare_editor_context
from promptune.core.exceptions import InvalidInputError
from promptune.modules.agent.model import Agent
from promptune.modules.message.model import Message
from promptune.modules.prompt.model import Prompt
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session


@pytest.fixture
def conversation():
    agent = Agent(id=uuid4(), context="Business context")
    prompt = Prompt(id=uuid4(), agent_id=agent.id, content="Original Markdown")
    session = Session(
        id=uuid4(),
        agent_id=agent.id,
        agent=agent,
        base_prompt_id=prompt.id,
        base_prompt=prompt,
    )
    now = datetime.now(UTC)
    previous = [
        Message(
            id=UUID(int=i + 1),
            session_id=session.id,
            created_at=now + timedelta(seconds=i),
            role="assistant",
            content=f"Explanation {i}",
            proposal=None,
            questions=["Excluded question"],
            warnings=["Excluded warning"],
        )
        for i in range(2)
    ]
    current = Message(
        id=uuid4(),
        session_id=session.id,
        created_at=now + timedelta(seconds=3),
        role="user",
        content="Shorten it",
        base_proposal_id=None,
    )
    return session, current, previous


def add_proposal(message, identifier, content):
    return PromptProposal(
        id=UUID(int=identifier),
        message=message,
        message_id=message.id,
        created_at=message.created_at,
        proposed_content=content,
        summary=["Excluded summary"],
        status="discarded",
    )


def test_original_and_history_order(conversation):
    session, current, previous = conversation
    result = prepare_editor_context(session, current, list(reversed(previous)))
    assert result.base_prompt_content == "Original Markdown"
    assert result.agent_context == "Business context"
    assert [m.content for m in result.messages] == [
        "Explanation 0",
        "Explanation 1",
        "Shorten it",
    ]
    assert all(set(m.model_dump()) == {"role", "content"} for m in result.messages)


def test_latest_and_explicit_old_proposal(conversation):
    session, current, previous = conversation
    older = add_proposal(previous[0], 10, "Older Markdown")
    add_proposal(previous[1], 11, "Latest Markdown")
    current.reply_to_id = previous[0].id
    latest_context = prepare_editor_context(session, current, previous)
    assert latest_context.base_prompt_content == "Latest Markdown"
    assert "Older Markdown" not in str(latest_context.messages)
    current.base_proposal_id = older.id
    current.base_proposal = older
    assert (
        prepare_editor_context(session, current, previous).base_prompt_content
        == "Older Markdown"
    )


def test_proposal_timestamp_tie_uses_id(conversation):
    session, current, previous = conversation
    first = add_proposal(previous[0], 30, "Higher ID")
    second = add_proposal(previous[1], 20, "Lower ID")
    second.created_at = first.created_at
    assert (
        prepare_editor_context(session, current, previous).base_prompt_content
        == "Higher ID"
    )


@pytest.mark.parametrize(
    "case",
    [
        "foreign_message",
        "missing_base",
        "foreign_base",
        "unloaded",
        "duplicate",
        "future",
    ],
)
def test_invalid_context(conversation, case):
    session, current, previous = conversation
    if case == "foreign_message":
        previous[0].session_id = uuid4()
    elif case == "missing_base":
        current.base_proposal_id = uuid4()
        current.base_proposal = None
    elif case == "foreign_base":
        proposal = add_proposal(previous[0], 10, "Other session")
        current.base_proposal_id = proposal.id
        current.base_proposal = proposal
        previous[0].session_id = uuid4()
        previous = []
    elif case == "unloaded":
        del session.agent
    elif case == "duplicate":
        previous.append(current)
    else:
        previous[0].created_at = current.created_at + timedelta(seconds=1)
    with pytest.raises(InvalidInputError):
        prepare_editor_context(session, current, previous)


