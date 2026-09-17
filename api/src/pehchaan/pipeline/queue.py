"""Bounded work queue: fixed concurrency per process, backpressure instead of collapse.

Registration deadlines are spiky. Each process runs at most `workers` verifications at a time and holds at most
`queue_size` waiting; beyond that the API answers 429 with Retry-After so Hackingly's client backs off. A sync
request that waits longer than its budget is answered 202 and finishes in the background (webhook + polling).
In production the in-process queue becomes SQS/Redis and workers scale horizontally on queue depth.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pehchaan.domain.models import Job, VerificationResult

logger = logging.getLogger(__name__)

MAX_REMEMBERED_JOBS = 10_000


class QueueFullError(RuntimeError):
    pass


@dataclass
class _Task:
    job_id: str
    tenant: str
    run: Callable[[], Awaitable[VerificationResult]]
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())


class VerificationQueue:
    def __init__(self, workers: int, size: int) -> None:
        self._queue: asyncio.Queue[_Task] = asyncio.Queue(maxsize=size)
        self._workers = workers
        self._tasks: list[asyncio.Task] = []
        self._jobs: OrderedDict[str, tuple[str, Job]] = OrderedDict()
        self.running = 0

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._worker(i)) for i in range(self._workers)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    def submit(self, tenant: str, run: Callable[[], Awaitable[VerificationResult]]) -> _Task:
        task = _Task(job_id=f"job_{uuid.uuid4().hex}", tenant=tenant, run=run)
        # A caller that stopped waiting (202) must not leave an unobserved exception behind.
        task.future.add_done_callback(lambda f: f.cancelled() or f.exception())
        try:
            self._queue.put_nowait(task)
        except asyncio.QueueFull as exc:
            raise QueueFullError from exc
        self._remember(task.job_id, tenant, Job(job_id=task.job_id, status="queued"))
        return task

    def job(self, job_id: str, tenant: str) -> Job | None:
        entry = self._jobs.get(job_id)
        return entry[1] if entry and entry[0] == tenant else None

    async def _worker(self, index: int) -> None:
        while True:
            task = await self._queue.get()
            self.running += 1
            self._remember(task.job_id, task.tenant, Job(job_id=task.job_id, status="running"))
            try:
                result = await task.run()
                self._remember(
                    task.job_id,
                    task.tenant,
                    Job(job_id=task.job_id, status="done", verification_id=result.verification_id),
                )
                if not task.future.done():
                    task.future.set_result(result)
            except Exception as exc:
                logger.error("verification job failed: %s", type(exc).__name__)
                self._remember(
                    task.job_id, task.tenant, Job(job_id=task.job_id, status="failed", error="internal error")
                )
                if not task.future.done():
                    task.future.set_exception(exc)
            finally:
                self.running -= 1
                self._queue.task_done()

    def _remember(self, job_id: str, tenant: str, job: Job) -> None:
        self._jobs[job_id] = (tenant, job)
        self._jobs.move_to_end(job_id)
        while len(self._jobs) > MAX_REMEMBERED_JOBS:
            self._jobs.popitem(last=False)
