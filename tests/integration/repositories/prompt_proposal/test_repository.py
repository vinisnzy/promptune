from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from promptune.agents.prompt_editor.schema import PromptProposalOutput
from promptune.core.exceptions import ConflictError
from promptune.modules.message.model import MessageRole
from promptune.modules.message.repository import MessageRepository
from promptune.modules.prompt.repository import PromptRepository
from promptune.modules.prompt_proposal.model import PromptProposalStatus
from promptune.modules.prompt_proposal.repository import PromptProposalRepository
from promptune.modules.session.repository import SessionRepository
from tests.integration.repositories._conversation import setup_conversation

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def create_proposal(session: AsyncSession):
    owner, other, agent, prompt, _ = await setup_conversation(session)
    conversation = await SessionRepository(session).create(
        user_id=owner.id, agent_id=agent.id, base_prompt_id=prompt.id
    )
    user_message = await MessageRepository(session).create(
        session_id=conversation.id,
        user_id=owner.id,
        role=MessageRole.USER,
        content="Improve greeting",
    )
    assistant = await MessageRepository(session).create(
        session_id=conversation.id,
        user_id=owner.id,
        role=MessageRole.ASSISTANT,
        content="I prepared a proposal",
        reply_to_id=user_message.id,
    )
    proposal = await PromptProposalRepository(session).create_for_message(
        message_id=assistant.id,
        agent_id=agent.id,
        source_prompt_id=prompt.id,
        change_request=user_message.content,
        output=PromptProposalOutput(
            proposed_content="# Improved",
            proposed_description="Improved greeting",
            summary=["Updated greeting"],
        ),
        questions=[],
        warnings=["Review before publishing"],
    )
    return owner, other, agent, prompt, proposal


async def test_owned_proposal_can_be_listed_and_approved(
    session: AsyncSession,
) -> None:
    owner, other, agent, source, proposal = await create_proposal(session)
    repository = PromptProposalRepository(session)
    await PromptRepository(session).add_prompt(
        {"agent_id": agent.id, "content": "A newer version"}
    )

    assert await repository.get_by_id(proposal.id, other.id) is None
    assert await repository.list_by_agent(agent.id, other.id, 1, 10) == []
    assert await repository.list_by_agent(agent.id, owner.id, 1, 10) == [proposal]
    approved = await repository.approve(proposal.id, owner.id)
    current = await PromptRepository(session).get_current_prompt_by_agent(agent.id)

    assert approved is proposal
    assert proposal.status == PromptProposalStatus.APPROVED
    assert current is not None
    assert current.version == 3
    assert current.content == proposal.proposed_content
    assert proposal.source_prompt_id == source.id
    assert proposal.approved_prompt_id == current.id
    with pytest.raises(ConflictError):
        await repository.approve(proposal.id, owner.id)


async def test_owned_proposal_can_be_discarded_without_creating_version(
    session: AsyncSession,
) -> None:
    owner, other, agent, source, proposal = await create_proposal(session)
    repository = PromptProposalRepository(session)

    assert await repository.discard(proposal.id, other.id) is None
    assert await repository.discard(proposal.id, owner.id) is proposal
    assert proposal.status == PromptProposalStatus.DISCARDED
    current = await PromptRepository(session).get_current_prompt_by_agent(agent.id)
    assert current is not None and current.id == source.id
    with pytest.raises(ConflictError):
        await repository.discard(proposal.id, owner.id)
    assert await repository.get_by_id(uuid4(), owner.id) is None
