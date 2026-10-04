from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import inspect

from promptune.agents.prompt_editor.schema import EditorMessage
from promptune.core.exceptions import InvalidInputError
from promptune.modules.message.model import Message
from promptune.modules.session.model import Session


@dataclass(frozen=True)
class EditorContext:
    agent_context: str | None
    messages: tuple[EditorMessage, ...]
    base_prompt_content: str


def _loaded(obj, name: str):
    if name in inspect(obj).unloaded:
        raise InvalidInputError(f"{type(obj).__name__}.{name} must be loaded")
    return getattr(obj, name)


def _key(obj):
    timestamp, identifier = _loaded(obj, "created_at"), _loaded(obj, "id")
    if timestamp is None or identifier is None:
        raise InvalidInputError("History objects require id and created_at")
    return timestamp, identifier


def prepare_editor_context(
    session: Session,
    current_message: Message,
    previous_messages: Sequence[Message],
) -> EditorContext:
    """Prepare editor inputs from loaded objects without issuing database queries."""
    session_id = _loaded(session, "id")
    current_key = _key(current_message)
    if session_id is None or _loaded(current_message, "role") != "user":
        raise InvalidInputError("A session and current user message are required")
    seen = {current_key[1]}
    for message in [current_message, *previous_messages]:
        if _loaded(message, "session_id") != session_id:
            raise InvalidInputError("Message belongs to another session")
    for message in previous_messages:
        key = _key(message)
        if key[1] in seen or key[0] > current_key[0]:
            raise InvalidInputError("Duplicate or future message in history")
        seen.add(key[1])
    ordered = sorted(previous_messages, key=_key)
    agent = _loaded(session, "agent")
    if agent is None or _loaded(agent, "id") != _loaded(session, "agent_id"):
        raise InvalidInputError("Session agent is missing or inconsistent")

    base_id = _loaded(current_message, "base_proposal_id")
    if base_id is not None:
        # Use the explicitly selected proposal in the user message
        proposal = _loaded(current_message, "base_proposal")
        if proposal is None or _loaded(proposal, "id") != base_id:
            raise InvalidInputError("Selected proposal is missing or inconsistent")
        owner = _loaded(proposal, "message")
        if (
            owner is None
            or _loaded(owner, "session_id") != session_id
            or _loaded(owner, "id") != _loaded(proposal, "message_id")
        ):
            raise InvalidInputError("Selected proposal must belong to this session")
    else:
        # Without explicit selection, it seeks the most recent proposal in history
        proposals = []
        for message in ordered:
            candidate = _loaded(message, "proposal")
            if candidate is not None:
                if _loaded(candidate, "message_id") != _loaded(message, "id"):
                    raise InvalidInputError("Proposal message is inconsistent")
                proposals.append(candidate)
        proposal = max(proposals, key=_key, default=None)
    if proposal is not None:
        # Uses the Markdown of the chosen proposal as the basis for editing.
        base_content = _loaded(proposal, "proposed_content")
    else:
        # With no proposals available, uses the original session prompt.
        prompt = _loaded(session, "base_prompt")
        if (
            prompt is None
            or _loaded(prompt, "id") != _loaded(session, "base_prompt_id")
            or _loaded(prompt, "agent_id") != _loaded(session, "agent_id")
        ):
            raise InvalidInputError("Session base prompt is missing or inconsistent")
        base_content = _loaded(prompt, "content")
    if not base_content.strip():
        raise InvalidInputError("Base prompt must not be blank")
    return EditorContext(
        agent_context=_loaded(agent, "context"),
        messages=tuple(
            EditorMessage(role=_loaded(item, "role"), content=_loaded(item, "content"))
            for item in [*ordered, current_message]
        ),
        base_prompt_content=base_content,
    )
