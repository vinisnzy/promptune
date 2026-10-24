import argparse
import asyncio
import contextlib
import logging
import signal

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from langchain.chat_models import init_chat_model

from promptune.agents.prompt_editor.agent import PromptEditorAgent
from promptune.agents.prompt_editor.configuration import load_editor_system_prompt
from promptune.core.config import Settings, get_settings
from promptune.core.logging import setup_logging
from promptune.database.session import build_engine, build_session_maker
from promptune.modules.agent_run.processor import AgentRunProcessor, ProcessResult
from promptune.modules.agent_run.queue import (
    RabbitRunPublisher,
    declare_topology,
    parse_run_id,
)

logger = logging.getLogger(__name__)

SHUTDOWN_MARGIN_SECONDS = 10


class RunConsumer:
    def __init__(self, processor: AgentRunProcessor) -> None:
        self.processor = processor

    async def handle(self, message: AbstractIncomingMessage) -> None:
        try:
            run_id = parse_run_id(message.body)
        except (ValueError, KeyError, TypeError):
            logger.error(
                "Discarding malformed agent run message",
                extra={"event": "agent_run_message_malformed"},
            )
            await message.reject(requeue=False)
            return
        result = await self.processor.process(run_id)
        if result == ProcessResult.ACK:
            await message.ack()
        else:
            await message.nack(requeue=True)


def chat_model_options(settings: Settings) -> dict[str, str]:
    options = {"model": settings.llm_model, "model_provider": settings.llm_provider}
    if settings.llm_api_key is not None:
        options["api_key"] = settings.llm_api_key.get_secret_value()
    if settings.llm_base_url:
        options["base_url"] = settings.llm_base_url
    return options


async def run_worker(*, once: bool = False) -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_maker = build_session_maker(engine)
    model = init_chat_model(**chat_model_options(settings))
    publisher = await RabbitRunPublisher.connect(
        settings.rabbitmq_url,
        retry_delay_seconds=settings.agent_run_retry_delay_seconds,
    )
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.worker_prefetch)
        topology = await declare_topology(
            channel, retry_delay_seconds=settings.agent_run_retry_delay_seconds
        )
        consumer = RunConsumer(
            AgentRunProcessor(
                session_maker,
                PromptEditorAgent(model, load_editor_system_prompt()),
                publisher,
                max_attempts=settings.agent_run_max_attempts,
                timeout_seconds=settings.agent_run_timeout_seconds,
            )
        )
        if once:
            message = await topology.process_queue.get(fail=False)
            if message is not None:
                await consumer.handle(message)
            return
        await _consume_until_stopped(
            topology.process_queue,
            consumer,
            grace_seconds=settings.agent_run_timeout_seconds + SHUTDOWN_MARGIN_SECONDS,
        )
    finally:
        await connection.close()
        await publisher.close()
        await engine.dispose()


async def _consume_until_stopped(
    queue, consumer: RunConsumer, *, grace_seconds: float
) -> None:
    stop = asyncio.Event()
    in_flight: set[asyncio.Task] = set()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Not supported on Windows; there Ctrl+C cancels this task instead.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    async def on_message(message: AbstractIncomingMessage) -> None:
        task = asyncio.current_task()
        in_flight.add(task)
        try:
            await consumer.handle(message)
        finally:
            in_flight.discard(task)

    consumer_tag = await queue.consume(on_message)
    logger.info("Worker consuming", extra={"event": "worker_started"})
    try:
        await stop.wait()
    finally:
        logger.info("Worker stopping", extra={"event": "worker_stopping"})
        with contextlib.suppress(Exception):
            await queue.cancel(consumer_tag)
        if in_flight:
            _, pending = await asyncio.wait(in_flight, timeout=grace_seconds)
            for task in pending:
                # Unacked messages return to the queue and are redelivered.
                task.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued Promptune agent runs")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued message and exit",
    )
    args = parser.parse_args()
    setup_logging()
    try:
        asyncio.run(run_worker(once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
