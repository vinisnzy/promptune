from promptune.agents.prompt_revision.agent import IPromptRevisionAgent
from promptune.schemas.revision import RevisionDraft


class FakePromptRevisionAgent(IPromptRevisionAgent):
    async def generate(
        self,
        source_content: str,
        source_description: str,
        agent_context: str | None,
        change_request: str,
    ) -> RevisionDraft:
        return RevisionDraft(
            proposed_content=source_content,
            proposed_description=f"Revisão simulada: {source_description}"[:200],
            summary=["Simulação: nenhuma alteração foi aplicada ao prompt."],
            questions=[],
            warnings=["Resultado simulado, sem uso de IA. Revise antes de aprovar."],
        )
