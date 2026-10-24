import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from promptune.core.config import Settings
from promptune.modules.agent_run.processor import ProcessResult
from promptune.modules.agent_run.worker import RunConsumer, chat_model_options


def make_message(body: bytes) -> AsyncMock:
    message = AsyncMock()
    message.body = body
    return message


async def test_should_ack_message_when_processor_acks() -> None:
    run_id = uuid4()
    processor = MagicMock(process=AsyncMock(return_value=ProcessResult.ACK))
    message = make_message(json.dumps({"run_id": str(run_id)}).encode())

    await RunConsumer(processor).handle(message)

    processor.process.assert_awaited_once_with(run_id)
    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()


async def test_should_nack_with_requeue_when_processor_requests_it() -> None:
    processor = MagicMock(
        process=AsyncMock(return_value=ProcessResult.NACK_REQUEUE)
    )
    message = make_message(json.dumps({"run_id": str(uuid4())}).encode())

    await RunConsumer(processor).handle(message)

    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_awaited()


async def test_should_reject_malformed_message_without_requeue() -> None:
    processor = MagicMock(process=AsyncMock())
    message = make_message(b"not json")

    await RunConsumer(processor).handle(message)

    processor.process.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


def make_settings(**overrides) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/unused",
        jwt_secret="test-secret-for-unit-tests-at-least-32-bytes",
        jwt_algorithm="HS256",
        llm_model="gpt-4.1-mini",
        llm_provider="openai",
        _env_file=None,
        **overrides,
    )


def test_should_pass_api_key_and_base_url_when_configured() -> None:
    settings = make_settings(llm_api_key="secret", llm_base_url="http://llm:8000/v1")

    assert chat_model_options(settings) == {
        "model": "gpt-4.1-mini",
        "model_provider": "openai",
        "api_key": "secret",
        "base_url": "http://llm:8000/v1",
    }


def test_should_omit_api_key_and_base_url_when_absent() -> None:
    assert chat_model_options(make_settings()) == {
        "model": "gpt-4.1-mini",
        "model_provider": "openai",
    }
