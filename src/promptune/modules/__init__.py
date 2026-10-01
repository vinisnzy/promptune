"""Register all module models in SQLAlchemy's shared metadata."""

from promptune.modules.agent.model import Agent
from promptune.modules.auth.models.refresh_token import RefreshToken
from promptune.modules.auth.models.user import User
from promptune.modules.prompt.model import Prompt
from promptune.modules.revision.model import Revision

__all__ = ["Agent", "Prompt", "RefreshToken", "Revision", "User"]
