import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractExchange,
    AbstractQueue,
    AbstractRobustChannel,
    AbstractRobustConnection,
)
from fastapi import Request

from promptune.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

EXCHANGE = "agent_runs"
DEAD_EXCHANGE = "agent_runs.dead"
PROCESS_QUEUE = "agent_runs.process"
RETRY_QUEUE = "agent_runs.retry"
DEAD_QUEUE = "agent_runs.dead"
PROCESS_KEY = "process"
RETRY_KEY = "retry"
DEAD_KEY = "dead"

DEFAULT_DELIVERY_LIMIT = 5
PUBLISH_TIMEOUT_SECONDS = 5


class QueueUnavailableError(ServiceUnavailableError):
    def __init__(self) -> None:
        super().__init__("The processing queue is temporarily unavailable")


@dataclass(frozen=True)
class Topology:
    exchange: AbstractExchange
    process_queue: AbstractQueue


async def declare_topology(
    channel: AbstractRobustChannel,
    *,
    retry_delay_seconds: int,
    delivery_limit: int = DEFAULT_DELIVERY_LIMIT,
) -> Topology:
    exchange = await channel.declare_exchange(
        EXCHANGE, ExchangeType.DIRECT, durable=True
    )
    dead_exchange = await channel.declare_exchange(
        DEAD_EXCHANGE, ExchangeType.DIRECT, durable=True
    )
    process_queue = await channel.declare_queue(
        PROCESS_QUEUE,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-delivery-limit": delivery_limit,
            "x-dead-letter-exchange": DEAD_EXCHANGE,
            "x-dead-letter-routing-key": DEAD_KEY,
        },
    )
    await process_queue.bind(exchange, routing_key=PROCESS_KEY)
    # Quorum queues have no per-queue TTL, so the delayed retry queue is classic.
    retry_queue = await channel.declare_queue(
        RETRY_QUEUE,
        durable=True,
        arguments={
            "x-message-ttl": retry_delay_seconds * 1000,
            "x-dead-letter-exchange": EXCHANGE,
            "x-dead-letter-routing-key": PROCESS_KEY,
        },
    )
    await retry_queue.bind(exchange, routing_key=RETRY_KEY)
    dead_queue = await channel.declare_queue(DEAD_QUEUE, durable=True)
    await dead_queue.bind(dead_exchange, routing_key=DEAD_KEY)
    return Topology(exchange=exchange, process_queue=process_queue)


class IRunPublisher(ABC):
    @abstractmethod
    async def publish_run(self, run_id: UUID) -> None: ...

    @abstractmethod
    async def publish_retry(self, run_id: UUID) -> None: ...


class RabbitRunPublisher(IRunPublisher):
    def __init__(
        self,
        connection: AbstractRobustConnection,
        exchange: AbstractExchange,
    ) -> None:
        self.connection = connection
        self.exchange = exchange

    @classmethod
    async def connect(
        cls,
        url: str,
        *,
        retry_delay_seconds: int,
        delivery_limit: int = DEFAULT_DELIVERY_LIMIT,
    ) -> RabbitRunPublisher:
        connection = await aio_pika.connect_robust(url)
        channel = await connection.channel(publisher_confirms=True)
        topology = await declare_topology(
            channel,
            retry_delay_seconds=retry_delay_seconds,
            delivery_limit=delivery_limit,
        )
        return cls(connection, topology.exchange)

    async def close(self) -> None:
        await self.connection.close()

    async def publish_run(self, run_id: UUID) -> None:
        await self._publish(run_id, PROCESS_KEY)

    async def publish_retry(self, run_id: UUID) -> None:
        await self._publish(run_id, RETRY_KEY)

    async def _publish(self, run_id: UUID, routing_key: str) -> None:
        message = Message(
            json.dumps({"run_id": str(run_id)}).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(run_id),
        )
        try:
            async with asyncio.timeout(PUBLISH_TIMEOUT_SECONDS):
                await self.exchange.publish(message, routing_key=routing_key)
        except Exception as error:
            logger.exception(
                "Agent run publication failed",
                extra={"event": "agent_run_publish_failed", "run_id": str(run_id)},
            )
            raise QueueUnavailableError() from error


def parse_run_id(body: bytes) -> UUID:
    return UUID(json.loads(body)["run_id"])


def get_run_publisher(request: Request) -> IRunPublisher:
    return request.app.state.run_publisher
