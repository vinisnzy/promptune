from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from promptune.modules.agent.model import Agent
from promptune.modules.auth.models.user import User
from promptune.modules.prompt.model import Prompt


async def setup_conversation(session: AsyncSession):
    owner = User(email=f"{uuid4()}@example.com", hashed_password="hash")
    other = User(email=f"{uuid4()}@example.com", hashed_password="hash")
    agent = Agent(name="Editor", context="Scheduling rules")
    other_agent = Agent(name="Other")
    session.add_all([owner, other, agent, other_agent])
    await session.flush()
    prompt = Prompt(agent_id=agent.id, version=1, description="v1", content="Base")
    wrong_prompt = Prompt(
        agent_id=other_agent.id, version=1, description="v1", content="Wrong"
    )
    session.add_all([prompt, wrong_prompt])
    await session.flush()
    return owner, other, agent, prompt, wrong_prompt
