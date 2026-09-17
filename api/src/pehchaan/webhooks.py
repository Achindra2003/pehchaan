"""Signed webhooks to Hackingly: decisions and fraud events in real time."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid

import httpx

from pehchaan.config import Settings
from pehchaan.domain.models import VerificationResult

logger = logging.getLogger(__name__)

RETRY_DELAYS = (0.5, 2.0, 8.0)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class WebhookSender:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.webhook_url
        self._secret = settings.webhook_secret.get_secret_value()
        self._tasks: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._secret)

    def send(self, event: str, result: VerificationResult) -> None:
        if not self.enabled:
            return
        body = json.dumps(
            {
                "id": f"evt_{uuid.uuid4().hex}",
                "type": event,
                "data": json.loads(result.model_dump_json(exclude={"checks"})),
            },
            separators=(",", ":"),
        ).encode()
        task = asyncio.get_running_loop().create_task(self._deliver(body))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, body: bytes) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for attempt, delay in enumerate((0.0, *RETRY_DELAYS)):
                await asyncio.sleep(delay)
                timestamp = str(int(time.time()))
                headers = {
                    "Content-Type": "application/json",
                    "X-Pehchaan-Timestamp": timestamp,
                    "X-Pehchaan-Signature": sign(self._secret, timestamp, body),
                }
                try:
                    response = await client.post(self._url, content=body, headers=headers)
                    if response.status_code < 500:
                        return
                except httpx.HTTPError:
                    pass
                logger.warning("webhook delivery attempt %d failed", attempt + 1)
