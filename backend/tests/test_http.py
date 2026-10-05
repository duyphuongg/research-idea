import httpx
import pytest
import respx

from app.connectors.base import ConnectorError
from app.connectors.http import RateLimiter, request_with_retry

URL = "https://api.example.com/items"


class SleepRecorder:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@respx.mock
async def test_retries_on_503_then_succeeds():
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        resp = await request_with_retry(client, "GET", URL, sleep=sleep)
    assert resp.json() == {"ok": 1}
    assert route.call_count == 3
    assert sleep.calls == [1.0, 2.0]


@respx.mock
async def test_gives_up_after_three_retries():
    route = respx.get(URL).mock(return_value=httpx.Response(429))
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        with pytest.raises(ConnectorError, match="HTTP 429"):
            await request_with_retry(client, "GET", URL, sleep=sleep)
    assert route.call_count == 4
    assert sleep.calls == [1.0, 2.0, 4.0]


@respx.mock
async def test_client_error_is_not_retried():
    route = respx.get(URL).mock(return_value=httpx.Response(404, text="nope"))
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        with pytest.raises(ConnectorError, match="HTTP 404"):
            await request_with_retry(client, "GET", URL, sleep=sleep)
    assert route.call_count == 1
    assert sleep.calls == []


@respx.mock
async def test_transport_error_is_retried():
    respx.get(URL).mock(side_effect=[httpx.ConnectError("down"), httpx.Response(200)])
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        resp = await request_with_retry(client, "GET", URL, sleep=sleep)
    assert resp.status_code == 200
    assert sleep.calls == [1.0]


async def test_rate_limiter_waits_between_calls():
    sleep = SleepRecorder()
    limiter = RateLimiter(0.5, clock=lambda: 10.0, sleep=sleep)
    await limiter.wait()
    await limiter.wait()
    assert sleep.calls == [0.5]


async def test_rate_limiter_skips_wait_when_interval_elapsed():
    sleep = SleepRecorder()
    ticks = iter([0.0, 1.0, 1.0])
    limiter = RateLimiter(0.5, clock=lambda: next(ticks), sleep=sleep)
    await limiter.wait()
    await limiter.wait()
    assert sleep.calls == []
