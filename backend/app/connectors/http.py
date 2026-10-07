import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.connectors.base import ConnectorError

RETRY_STATUS = {429, 500, 502, 503, 504}

Sleep = Callable[[float], Awaitable[Any]]


class RateLimiter:
    """Enforces a minimum interval between consecutive requests."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            if self._last is not None:
                remaining = self.min_interval - (self._clock() - self._last)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last = self._clock()


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    sleep: Sleep = asyncio.sleep,
    limiter: RateLimiter | None = None,
    **kwargs: Any,
) -> httpx.Response:
    attempt = 0
    while True:
        if limiter is not None:
            await limiter.wait()
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt >= retries:
                raise ConnectorError(f"{method} {url}: {exc!r}") from exc
        else:
            if resp.status_code not in RETRY_STATUS:
                if resp.is_error:
                    raise ConnectorError(
                        f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]}",
                        status=resp.status_code,
                    )
                return resp
            if attempt >= retries:
                raise ConnectorError(
                    f"{method} {url}: HTTP {resp.status_code} after {retries} retries",
                    status=resp.status_code,
                )
        await sleep(backoff * 2**attempt)
        attempt += 1
