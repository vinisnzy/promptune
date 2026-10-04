from promptune.agents.prompt_editor.agent import IPromptEditorAgent
from promptune.modules.prompt_proposal.schema import PromptProposalDraft


class FakePromptEditorAgent(IPromptEditorAgent):
    async def respond(
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
