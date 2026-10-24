from uuid import UUID

from promptune.modules.agent_run.queue import IRunPublisher, QueueUnavailableError


class FakeRunPublisher(IRunPublisher):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[UUID] = []
        self.retried: list[UUID] = []

    async def publish_run(self, run_id: UUID) -> None:
        if self.fail:
            raise QueueUnavailableError()
        self.published.append(run_id)

    async def publish_retry(self, run_id: UUID) -> None:
        if self.fail:
            raise QueueUnavailableError()
        self.retried.append(run_id)
