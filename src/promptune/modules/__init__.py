"""Register all module models in SQLAlchemy's shared metadata."""

from promptune.modules.agent.model import Agent
from promptune.modules.auth.models.refresh_token import RefreshToken
from promptune.modules.auth.models.user import User
from promptune.modules.message.model import Message
from promptune.modules.prompt.model import Prompt
from promptune.modules.prompt_proposal.model import PromptProposal
from promptune.modules.session.model import Session

__all__ = [
    "Agent",
    "Message",
    "Prompt",
    "PromptProposal",
    "RefreshToken",
    "Session",
    "User",
]
