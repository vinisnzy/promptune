from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from promptune.agents.prompt_editor.agent import PromptEditorAgent
from promptune.agents.prompt_editor.schema import EditorMessage, PromptEditorResponse
from promptune.core.exceptions import InvalidInputError


@pytest.mark.parametrize(
    "proposal",
    [
        None,
        {
            "proposed_content": "New Markdown",
            "proposed_description": "Shorter",
            "summary": ["Shortened greeting"],
        },
    ],
)
async def test_agent_payload_and_response(proposal):
    messages = [
        EditorMessage(role="assistant", content="Previous explanation"),
        EditorMessage(role="user", content="Shorten it"),
    ]
    response = {
        "message": "Explanation",
        "questions": [],
        "warnings": [],
        "proposal": proposal,
    }
    runner = AsyncMock()
    runner.ainvoke.return_value = {"structured_response": response}
    with patch(
        "promptune.agents.prompt_editor.agent.create_agent", return_value=runner
    ) as factory:
        model = object()
        agent = PromptEditorAgent(model, "Editor instructions")
        actual = await agent.respond(
            agent_context="Business context",
            messages=messages,
            base_prompt_content="Selected Markdown",
        )
    factory.assert_called_once_with(
        model=model,
        tools=[],
        system_prompt="Editor instructions",
        response_format=PromptEditorResponse,
    )
    assert actual.model_dump() == response
    payload = runner.ainvoke.call_args.args[0]["messages"]
    assert payload[1:] == [m.model_dump() for m in messages]
    assert "Selected Markdown" in payload[0]["content"]
    assert "Business context" in payload[0]["content"]
    assert str(payload).count("Shorten it") == 1


@pytest.mark.parametrize(
    "response", [{}, {"structured_response": {"message": "Incomplete"}}]
)
async def test_invalid_agent_output(response):
    runner = AsyncMock()
    runner.ainvoke.return_value = response
    with patch(
        "promptune.agents.prompt_editor.agent.create_agent", return_value=runner
    ):
        agent = PromptEditorAgent(object(), "Instructions")
    with pytest.raises((InvalidInputError, ValidationError)):
        await agent.respond(
            agent_context=None,
            messages=[EditorMessage(role="user", content="Edit")],
            base_prompt_content="Markdown",
        )


@pytest.mark.parametrize(
    "messages", [[], [EditorMessage(role="assistant", content="Answer")]]
)
async def test_invalid_history(messages):
    with patch("promptune.agents.prompt_editor.agent.create_agent") as factory:
        agent = PromptEditorAgent(object(), "Instructions")
        with pytest.raises(InvalidInputError):
            await agent.respond(
                agent_context=None, messages=messages, base_prompt_content="Markdown"
            )
        factory.return_value.ainvoke.assert_not_called()
