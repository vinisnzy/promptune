from functools import cache
from importlib.resources import files


@cache
def load_editor_system_prompt() -> str:
    """Load the prompt editor agent system prompt."""
    prompt = (
        files("promptune.agents.prompt_editor")
        .joinpath("prompts", "editor.md")
        .read_text(encoding="utf-8")
    )
    if not prompt.strip():
        raise ValueError("Editor system prompt must not be blank")
    return prompt
