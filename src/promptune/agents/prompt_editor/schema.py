from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class EditorMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: str


class PromptProposalOutput(BaseModel):
    proposed_content: Annotated[
        str,
        Field(
            min_length=1,
            description="Complete Markdown content of the proposed prompt.",
        ),
    ]
    proposed_description: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="Short description of the proposed prompt version.",
        ),
    ]
    summary: list[str] = Field(
        description="Only the changes effectively made to the base prompt.",
    )


class PromptEditorResponse(BaseModel):
    message: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Response shown to the user, such as an explanation, clarification, "
                "or presentation of the proposal."
            ),
        ),
    ]
    questions: list[str] = Field(
        description="Questions that require an answer before editing can continue.",
    )
    warnings: list[str] = Field(
        description="Conflicts and risks identified while handling the request.",
    )
    proposal: PromptProposalOutput | None = Field(
        description=(
            "Proposed prompt when an edit was made. Null for explanations, questions, "
            "or requests that lack enough information."
        ),
    )
