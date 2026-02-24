"""Unit tests for src.api.base (RateLimiter, BaseAPIClient)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.api.base import BaseAPIClient, RateLimiter
from src.utils.errors import APIError, RateLimitError


def _run(coro):
    """Run async test without requiring pytest-asyncio."""
    return asyncio.run(coro)


# Concrete client for testing BaseAPIClient
class ConcreteAPIClient(BaseAPIClient):
    async def get_paper(self, paper_id: str):
        return await self._make_request("GET", f"paper/{paper_id}")


class TestRateLimiter:
    def test_init(self):
        limiter = RateLimiter(rate_limit=10, time_window=300)
        assert limiter.rate_limit == 10
        assert limiter.time_window == 300
        assert limiter.tokens == 10

    def test_acquire_consumes_one_token(self):
        async def _():
            limiter = RateLimiter(rate_limit=3, time_window=300)
            await limiter.acquire()
            assert limiter.tokens == 2
            await limiter.acquire()
            assert limiter.tokens == 1
            await limiter.acquire()
            assert limiter.tokens == 0

        _run(_())

    def test_acquire_blocks_when_no_tokens_then_refills(self):
        async def _():
            limiter = RateLimiter(rate_limit=1, time_window=1)
            await limiter.acquire()
            assert limiter.tokens == 0
            with patch("src.api.base.time.time") as mock_time:
                mock_time.return_value = 1000
                limiter.last_refill = 998  # 2 seconds ago
                await limiter.acquire()
            assert limiter.tokens == 0  # consumed the refilled token

        _run(_())

    def test_refill_after_time_window(self):
        async def _():
            limiter = RateLimiter(rate_limit=2, time_window=60)
            await limiter.acquire()
            await limiter.acquire()
            assert limiter.tokens == 0
            with patch("src.api.base.time.time", return_value=1000):
                limiter.last_refill = 939  # 61 seconds ago
                await limiter._refill_tokens()
            assert limiter.tokens == 2

        _run(_())


class TestBaseAPIClient:
    @pytest.fixture
    def rate_limiter(self):
        return RateLimiter(rate_limit=100, time_window=300)

    @pytest.fixture
    def client(self, rate_limiter):
        return ConcreteAPIClient(
            base_url="https://api.example.com/v1",
            rate_limiter=rate_limiter,
            timeout=10,
        )

    def test_make_request_success(self, client):
        async def _():
            client.client = AsyncMock()
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"paperId": "abc", "title": "Test"}
            response.raise_for_status = MagicMock()
            client.client.request = AsyncMock(return_value=response)
            result = await client._make_request("GET", "paper/abc")
            assert result == {"paperId": "abc", "title": "Test"}
            client.client.request.assert_called_once()
            call_kw = client.client.request.call_args[1]
            assert call_kw["method"] == "GET"
            assert "api.example.com/v1/paper/abc" in call_kw["url"]

        _run(_())

    def test_make_request_429_raises_rate_limit_error(self, client):
        async def _():
            client.client = AsyncMock()
            response = MagicMock()
            response.status_code = 429
            client.client.request = AsyncMock(return_value=response)
            with pytest.raises(RateLimitError, match="Rate limit exceeded"):
                await client._make_request("GET", "paper/abc")

        _run(_())

    def test_make_request_http_error_raises_api_error(self, client):
        async def _():
            client.client = AsyncMock()
            response = MagicMock()
            response.status_code = 404
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=response
            )
            client.client.request = AsyncMock(return_value=response)
            with pytest.raises(APIError, match="HTTP 404"):
                await client._make_request("GET", "paper/xyz")

        _run(_())

    def test_retry_with_backoff_succeeds_first_try(self, client):
        async def _():
            func = AsyncMock(return_value="ok")
            result = await client._retry_with_backoff(func)
            assert result == "ok"
            func.assert_called_once()

        _run(_())

    def test_retry_with_backoff_retries_then_succeeds(self, client):
        async def _():
            func = AsyncMock(side_effect=[APIError("fail"), APIError("fail"), "ok"])
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client._retry_with_backoff(func, max_retries=3)
            assert result == "ok"
            assert func.call_count == 3

        _run(_())

    def test_retry_with_backoff_reraises_rate_limit_immediately(self, client):
        async def _():
            func = AsyncMock(side_effect=RateLimitError("rate limited"))
            with pytest.raises(RateLimitError, match="rate limited"):
                await client._retry_with_backoff(func, max_retries=2)
            func.assert_called_once()

        _run(_())

    def test_retry_with_backoff_raises_after_max_retries(self, client):
        async def _():
            func = AsyncMock(side_effect=APIError("always fail"))
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(APIError, match="always fail"):
                    await client._retry_with_backoff(func, max_retries=2)
            assert func.call_count == 3

        _run(_())

    def test_close(self, client):
        async def _():
            client.client = AsyncMock()
            await client.close()
            client.client.aclose.assert_called_once()

        _run(_())
