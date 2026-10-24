import asyncio
import json
from uuid import uuid4

import aio_pika
import pytest
from aio_pika import DeliveryMode

from promptune.modules.agent_run.queue import (
    DEAD_QUEUE,
    PROCESS_QUEUE,
    RETRY_QUEUE,
    RabbitRunPublisher,
    declare_topology,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def get_one(channel, queue_name: str, *, wait: float = 0):
    queue = await channel.declare_queue(queue_name, passive=True)
    deadline = asyncio.get_running_loop().time() + wait
    while True:
        message = await queue.get(fail=False)
        if message is not None or asyncio.get_running_loop().time() >= deadline:
            return message
        await asyncio.sleep(0.1)


async def test_topology_declaration_is_idempotent(rabbitmq_url: str) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await declare_topology(channel, retry_delay_seconds=1)
        await declare_topology(channel, retry_delay_seconds=1)
        for name in (PROCESS_QUEUE, RETRY_QUEUE, DEAD_QUEUE):
            queue = await channel.declare_queue(name, passive=True)
            assert queue.name == name


async def test_publish_run_enqueues_persistent_message(rabbitmq_url: str) -> None:
    publisher = await RabbitRunPublisher.connect(rabbitmq_url, retry_delay_seconds=1)
    run_id = uuid4()
    try:
        await publisher.publish_run(run_id)
        connection = await aio_pika.connect_robust(rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            message = await get_one(channel, PROCESS_QUEUE, wait=5)
            assert message is not None
            assert json.loads(message.body) == {"run_id": str(run_id)}
            assert message.message_id == str(run_id)
            assert message.delivery_mode == DeliveryMode.PERSISTENT
            await message.ack()
    finally:
        await publisher.close()


async def test_publish_retry_returns_to_process_queue_after_delay(
    rabbitmq_url: str,
) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url)
    channel = await connection.channel()
    for name in (RETRY_QUEUE, PROCESS_QUEUE):
        await (await channel.declare_queue(name, passive=True)).purge()
    # The queue was declared with a 1s TTL by the earlier tests' publisher.
    publisher = await RabbitRunPublisher.connect(rabbitmq_url, retry_delay_seconds=1)
    run_id = uuid4()
    try:
        await publisher.publish_retry(run_id)
        assert await get_one(channel, PROCESS_QUEUE) is None
        message = await get_one(channel, PROCESS_QUEUE, wait=5)
        assert message is not None
        assert json.loads(message.body) == {"run_id": str(run_id)}
        await message.ack()
    finally:
        await publisher.close()
        await connection.close()
