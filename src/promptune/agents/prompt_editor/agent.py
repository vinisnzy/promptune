import json
from collections.abc import Sequence
from typing import Protocol

from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel

from promptune.agents.prompt_editor.schema import EditorMessage, PromptEditorResponse
from promptune.core.exceptions import InvalidInputError


class IPromptEditorAgent(Protocol):
    async def respond(
        self,
        *,
        agent_context: str | None,
        messages: Sequence[EditorMessage],
        base_prompt_content: str,
    ) -> PromptEditorResponse: ...


class PromptEditorAgent(IPromptEditorAgent):

    def __init__(self, model: BaseChatModel, system_prompt: str) -> None:
        if not system_prompt.strip():
            raise InvalidInputError("system_prompt must not be blank")
        self.agent = create_agent(
            model=model,
            tools=[],
            system_prompt=system_prompt,
            response_format=PromptEditorResponse,
        )

    async def respond(
        self,
        *,
        agent_context: str | None,
        messages: Sequence[EditorMessage],
        base_prompt_content: str,
    ) -> PromptEditorResponse:
        if not messages or messages[-1].role != "user":
            raise InvalidInputError("History must end with the current user message")
        if not base_prompt_content.strip():
            raise InvalidInputError("base_prompt_content must not be blank")
        task = {
            "base_prompt_content": base_prompt_content,
            "agent_context": agent_context,
        }

        result = await self.agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Dados da edição: contexto e documento a revisar.\n"
                        + json.dumps(task, ensure_ascii=False),
                    },
                    *(message.model_dump() for message in messages),
                ]
            }
        )
        if "structured_response" not in result:
            raise InvalidInputError("Agent did not return structured_response")
        return PromptEditorResponse.model_validate(result["structured_response"])
