import json
from typing import Protocol

from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel

from promptune.modules.revision.schema import RevisionDraft

SYSTEM_PROMPT = """
Você revisa prompts Markdown de agentes de triagem e agendamento.

Preserve regras de negócio, variáveis, nomes de ferramentas e instruções
essenciais. Faça somente as alterações solicitadas que sejam compatíveis
com o contexto do agente.

Se houver conflito ou informação insuficiente, preserve a instrução
existente e registre o problema em warnings ou questions. Não invente
requisitos, ferramentas ou regras.

Retorne:
- proposed_content: o Markdown completo proposto;
- proposed_description: uma descrição curta, com até 200 caracteres;
- summary: somente as mudanças que você efetivamente fez;
- questions: dúvidas que precisam de resposta;
- warnings: conflitos e riscos identificados.
"""


class IPromptRevisionAgent(Protocol):
    async def generate(
        self,
        source_content: str,
        source_description: str,
        agent_context: str | None,
        change_request: str,
    ) -> RevisionDraft: ...


class PromptRevisionAgent(IPromptRevisionAgent):
    def __init__(self, model: BaseChatModel) -> None:
        self.agent = create_agent(
            model=model,
            tools=[],
            system_prompt=SYSTEM_PROMPT,
            response_format=RevisionDraft,
        )

    async def generate(
        self,
        source_content: str,
        source_description: str,
        agent_context: str | None,
        change_request: str,
    ) -> RevisionDraft:
        task = {
            "source_content": source_content,
            "source_description": source_description,
            "agent_context": agent_context,
            "change_request": change_request,
        }

        result = await self.agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": json.dumps(task, ensure_ascii=False)}
                ]
            }
        )
        return RevisionDraft.model_validate(result["structured_response"])
