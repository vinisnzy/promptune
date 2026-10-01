"""Register all module models in SQLAlchemy's shared metadata."""

from promptune.modules.agent.model import Agent
from promptune.modules.auth.models.refresh_token import RefreshToken
from promptune.modules.auth.models.user import User
from promptune.modules.prompt.model import Prompt
from promptune.modules.prompt_proposal.model import PromptProposal

__all__ = ["Agent", "Prompt", "PromptProposal", "RefreshToken", "User"]
