import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from promptune.modules.agent_run.processor import ProcessResult
from promptune.modules.agent_run.worker import RunConsumer


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
