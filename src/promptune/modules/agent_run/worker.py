import argparse
import asyncio

from langchain.chat_models import init_chat_model

from promptune.agents.prompt_editor.agent import PromptEditorAgent
from promptune.agents.prompt_editor.configuration import load_editor_system_prompt
from promptune.core.config import get_settings
from promptune.core.logging import setup_logging
from promptune.database.session import build_engine, build_session_maker
from promptune.modules.agent_run.processor import AgentRunProcessor


async def run_worker(*, once: bool = False) -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_maker = build_session_maker(engine)
    model = init_chat_model(
        model=settings.llm_model,
        model_provider=settings.llm_provider,
        api_key=settings.groq_api_key.get_secret_value(),
    )
    processor = AgentRunProcessor(
        session_maker,
        PromptEditorAgent(model, load_editor_system_prompt()),
        lease_seconds=settings.agent_run_lease_seconds,
        heartbeat_seconds=settings.agent_run_heartbeat_seconds,
        max_attempts=settings.agent_run_max_attempts,
    )
    try:
        while True:
            processed = await processor.process_next()
            if once:
                return
            if not processed:
                await asyncio.sleep(settings.worker_poll_interval_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued Promptune agent runs")
    parser.add_argument(
        "--once", action="store_true", help="Process at most one run and exit"
    )
    args = parser.parse_args()
    setup_logging()
    try:
        asyncio.run(run_worker(once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
