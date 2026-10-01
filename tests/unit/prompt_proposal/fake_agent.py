from promptune.modules.prompt_proposal.agent import IPromptRevisionAgent
from promptune.modules.prompt_proposal.schema import PromptProposalDraft


class FakePromptRevisionAgent(IPromptRevisionAgent):
    async def generate(
        self,
        source_content: str,
        source_description: str,
        agent_context: str | None,
        change_request: str,
    ) -> PromptProposalDraft:
        return PromptProposalDraft(
            proposed_content=source_content,
            proposed_description=f"Revisão simulada: {source_description}"[:200],
            summary=["Simulação: nenhuma alteração foi aplicada ao prompt."],
            questions=[],
            warnings=["Resultado simulado, sem uso de IA. Revise antes de aprovar."],
        )
