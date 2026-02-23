"""Base API client with retry logic and rate limiting."""
import asyncio
import time
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import httpx
from src.utils.errors import APIError, RateLimitError
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate_limit: int, time_window: int = 300):
        """
        Initialize rate limiter.

        Args:
            rate_limit: Number of requests allowed
            time_window: Time window in seconds (default 300 = 5 minutes)
        """
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.tokens = rate_limit
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            await self._refill_tokens()

            while self.tokens <= 0:
                wait_time = self.time_window - (time.time() - self.last_refill)
                if wait_time > 0:
                    logger.warning(f"Rate limit reached. Waiting {wait_time:.1f}s")
                    await asyncio.sleep(min(wait_time, 10))
                await self._refill_tokens()

            self.tokens -= 1

    async def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        if elapsed >= self.time_window:
            self.tokens = self.rate_limit
            self.last_refill = now


class BaseAPIClient(ABC):
    """Abstract base API client with retry logic."""

    def __init__(
        self,
        base_url: str,
        rate_limiter: Optional[RateLimiter] = None,
        timeout: int = 30,
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL for API
            rate_limiter: Rate limiter instance (optional)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.rate_limiter = rate_limiter
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with optional rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            headers: Request headers

        Returns:
            JSON response as dictionary

        Raises:
            RateLimitError: If rate limit exceeded
            APIError: If request fails
        """
        # Only use rate limiter if provided
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        url = f"{self.base_url}/{endpoint}"

        try:
            response = await self.client.request(
                method=method, url=url, params=params, headers=headers
            )

            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")

            response.raise_for_status()

            # Simple delay after successful request
            await asyncio.sleep(0.2)

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise APIError(f"HTTP {e.response.status_code}: {str(e)}")
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise APIError(f"Request failed: {str(e)}")

    async def _retry_with_backoff(
        self,
        func,
        max_retries: int = 10,
        delay: float = 5.0,
    ):
        """
        Retry function with fixed delay.

        Args:
            func: Async function to retry
            max_retries: Maximum number of retries
            delay: Fixed delay between retries in seconds

        Returns:
            Result of successful function call

        Raises:
            Exception from last failed attempt
        """
        last_exception: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return await func()
            except RateLimitError:
                last_exception = RateLimitError("Rate limit exceeded")
                if attempt < max_retries:
                    wait_time = delay * (attempt + 1)
                    logger.warning(
                        f"Rate limited. Waiting {wait_time}s before retry "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(wait_time)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)

        if last_exception:
            raise last_exception
        raise APIError("All retries failed")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    @abstractmethod
    async def get_paper(self, paper_id: str) -> Dict[str, Any]:
        """Get paper metadata. Must be implemented by subclass."""
        pass
