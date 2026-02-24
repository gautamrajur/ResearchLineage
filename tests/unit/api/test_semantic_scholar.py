"""Unit tests for src.api.semantic_scholar (SemanticScholarClient)."""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.semantic_scholar import SemanticScholarClient
from src.utils.errors import APIError, RateLimitError


def _run(coro):
    return asyncio.run(coro)


# Minimal paper dict that validates as PaperResponse
def _valid_paper(paper_id: str = "test_id", title: str = "Test Paper"):
    return {
        "paperId": paper_id,
        "title": title,
        "abstract": None,
        "year": 2020,
        "citationCount": 0,
        "influentialCitationCount": 0,
        "referenceCount": 0,
        "authors": [],
        "externalIds": None,
        "venue": None,
        "publicationDate": None,
        "url": None,
    }


@pytest.fixture
def client():
    return SemanticScholarClient(cache=None)


class TestSemanticScholarClient:
    def test_get_headers_includes_api_key_when_set(self, client):
        client.api_key = "secret"
        assert client._get_headers() == {"x-api-key": "secret"}

    def test_get_headers_empty_when_no_api_key(self, client):
        client.api_key = ""
        assert client._get_headers() == {}

    def test_get_paper_returns_cached_when_hit(self, client):
        client.cache = type("Cache", (), {"get": lambda self, k: _valid_paper("cached", "Cached")})()
        client._make_request = AsyncMock()
        result = _run(client.get_paper("paper_123"))
        assert result["paperId"] == "cached"
        assert result["title"] == "Cached"
        client._make_request.assert_not_called()

    def test_get_paper_fetches_and_validates_when_cache_miss(self, client):
        client._make_request = AsyncMock(return_value=_valid_paper("fetched", "Fetched"))

        async def _retry_mock(f):
            return await f()

        client._retry_with_backoff = _retry_mock
        result = _run(client.get_paper("paper_456"))
        assert result["paperId"] == "fetched"
        assert result["title"] == "Fetched"
        client._make_request.assert_called_once()
        call_kw = client._make_request.call_args[1]
        assert call_kw["method"] == "GET"
        assert "paper/paper_456" in call_kw["endpoint"]
        assert "fields" in call_kw["params"]

    def test_get_references_returns_cached_when_hit(self, client):
        cached = [{"fromPaperId": "a", "toPaperId": "b", "citedPaper": _valid_paper()}]
        client.cache = type("Cache", (), {"get": lambda self, k: cached})()
        client._make_request = AsyncMock()
        result = _run(client.get_references("paper_1", limit=10, offset=0))
        assert result == cached
        client._make_request.assert_not_called()

    def test_get_references_fetches_and_extracts_data(self, client):
        client._make_request = AsyncMock(return_value={"data": [{"fromPaperId": "p1", "toPaperId": "p2"}]})

        async def _retry_mock(f):
            return await f()

        client._retry_with_backoff = _retry_mock
        result = _run(client.get_references("paper_1", limit=5, offset=0))
        assert len(result) == 1
        assert result[0]["fromPaperId"] == "p1"
        client._make_request.assert_called_once()
        assert "references" in client._make_request.call_args[1]["endpoint"]

    def test_get_citations_returns_empty_when_response_empty(self, client):
        client._make_request = AsyncMock(return_value={})

        async def _retry_mock(f):
            return await f()

        client._retry_with_backoff = _retry_mock
        result = _run(client.get_citations("paper_1", limit=10, offset=0))
        assert result == []


class TestSemanticScholarHTTPTransport:
    """Tests that use real HTTP path with mocked transport (no internal method mocking)."""

    def test_get_paper_via_http_transport(self, client):
        """get_paper succeeds when transport returns valid paper JSON."""
        payload = _valid_paper("http_id", "HTTP Fetched")

        def _handler(request: httpx.Request) -> httpx.Response:
            assert "paper/" in str(request.url)
            return httpx.Response(200, json=payload)

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        result = _run(client.get_paper("http_id"))
        assert result["paperId"] == "http_id"
        assert result["title"] == "HTTP Fetched"

    def test_get_paper_429_raises_rate_limit_error(self, client):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        with pytest.raises(RateLimitError, match="Rate limit"):
            _run(client.get_paper("p1"))

    def test_get_paper_500_raises_api_error(self, client):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Server Error")

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        with pytest.raises(APIError):
            _run(client.get_paper("p1"))

    def test_get_references_pagination_params(self, client):
        """get_references passes limit and offset to the API."""
        seen_params = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            seen_params["params"] = dict(request.url.params)
            return httpx.Response(200, json={"data": []})

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        _run(client.get_references("paper_1", limit=5, offset=20))
        assert seen_params["params"].get("limit") == "5"
        assert seen_params["params"].get("offset") == "20"

    def test_get_citations_pagination_params(self, client):
        """get_citations passes limit and offset."""
        seen_params = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            seen_params["params"] = dict(request.url.params)
            return httpx.Response(200, json={"data": []})

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        _run(client.get_citations("paper_1", limit=50, offset=10))
        assert seen_params["params"].get("limit") == "50"
        assert seen_params["params"].get("offset") == "10"
