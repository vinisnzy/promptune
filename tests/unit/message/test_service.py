from uuid import UUID, uuid4

import pytest

from promptune.core.exceptions import ConflictError, InvalidInputError, NotFoundError
from promptune.modules.message.model import MessageRole
from promptune.modules.message.schema import MessageSend
from promptune.modules.message.service import MessageService
from promptune.modules.session.model import Session
from promptune.modules.session.schema import SessionCreate
from promptune.modules.session.service import SessionService
from tests.unit.message.in_memory_repository import InMemoryMessageRepository


async def create_session(service: SessionService, user_id: UUID) -> Session:
    return await service.create_session(
        user_id, SessionCreate(agent_id=uuid4(), base_prompt_id=uuid4())
    )


async def test_should_send_normalized_user_message(
    session_service: SessionService,
    message_service: MessageService,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)

    dispatch = await message_service.send_message(
        conversation.id, owner_id, MessageSend(content="  Improve greeting  ")
    )
    message = dispatch.message

    assert message.session_id == conversation.id
    assert message.role == MessageRole.USER
    assert message.content == "Improve greeting"
    assert message.reply_to_id is None
    assert message.base_proposal_id is None
    assert message.questions == []
    assert message.warnings == []
    assert dispatch.run.session_id == conversation.id
    assert dispatch.run.user_message_id == message.id
    assert dispatch.run.status == "queued"
    assert (
        await message_service.get_message_by_id(message.id, conversation.id, owner_id)
        is message
    )


async def test_should_send_message_from_proposal_in_same_session(
    session_service: SessionService,
    message_service: MessageService,
    message_repository: InMemoryMessageRepository,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)
    proposal_id = uuid4()
    message_repository.add_proposal(proposal_id, conversation.id)

    dispatch = await message_service.send_message(
        conversation.id,
        owner_id,
        MessageSend(content="Revise again", base_proposal_id=proposal_id),
    )

    assert dispatch.message.base_proposal_id == proposal_id


async def test_should_reject_proposal_from_another_session(
    session_service: SessionService,
    message_service: MessageService,
    message_repository: InMemoryMessageRepository,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)
    other_session = await create_session(session_service, owner_id)
    proposal_id = uuid4()
    message_repository.add_proposal(proposal_id, other_session.id)

    with pytest.raises(InvalidInputError):
        await message_service.send_message(
            conversation.id,
            owner_id,
            MessageSend(content="Revise", base_proposal_id=proposal_id),
        )


async def test_should_list_messages_in_chronological_pages(
    session_service: SessionService,
    message_service: MessageService,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)
    first = (
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="First")
        )
    ).message
    # Finish the first run to model the sequential application flow.
    first_run = next(iter(message_service.agent_run_repository.runs.values()))
    first_run.status = "completed"
    second = (
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="Second")
        )
    ).message

    assert await message_service.list_messages(conversation.id, owner_id, 1, 1) == [
        first
    ]
    assert await message_service.list_messages(conversation.id, owner_id, 2, 1) == [
        second
    ]


async def test_should_isolate_messages_by_owner_and_session(
    session_service: SessionService,
    message_service: MessageService,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    conversation = await create_session(session_service, owner_id)
    other_session = await create_session(session_service, owner_id)
    message = (
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="Private")
        )
    ).message

    with pytest.raises(NotFoundError):
        await message_service.get_message_by_id(message.id, conversation.id, other_id)
    with pytest.raises(NotFoundError):
        await message_service.get_message_by_id(message.id, other_session.id, owner_id)
    with pytest.raises(NotFoundError):
        await message_service.list_messages(conversation.id, other_id, 1, 10)
    with pytest.raises(NotFoundError):
        await message_service.send_message(
            conversation.id, other_id, MessageSend(content="Intrusion")
        )


async def test_should_reject_blank_content_and_completed_session(
    session_service: SessionService,
    message_service: MessageService,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)

    with pytest.raises(InvalidInputError):
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="   ")
        )
    await session_service.complete_session(conversation.id, owner_id)
    with pytest.raises(ConflictError):
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="Too late")
        )


async def test_should_hide_messages_when_session_is_deleted(
    session_service: SessionService,
    message_service: MessageService,
) -> None:
    owner_id = uuid4()
    conversation = await create_session(session_service, owner_id)
    message = (
        await message_service.send_message(
            conversation.id, owner_id, MessageSend(content="Temporary")
        )
    ).message

    await session_service.delete_session(conversation.id, owner_id)

    with pytest.raises(NotFoundError):
        await message_service.get_message_by_id(message.id, conversation.id, owner_id)
    with pytest.raises(NotFoundError):
        await message_service.list_messages(conversation.id, owner_id, 1, 10)


async def test_should_reject_invalid_message_queries(
    message_service: MessageService,
) -> None:
    with pytest.raises(InvalidInputError):
        await message_service.list_messages(uuid4(), uuid4(), 0, 10)
    with pytest.raises(InvalidInputError):
        await message_service.list_messages(uuid4(), uuid4(), 1, 0)
    with pytest.raises(NotFoundError):
        await message_service.get_message_by_id(uuid4(), uuid4(), uuid4())
