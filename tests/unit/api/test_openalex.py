"""Unit tests for src.api.openalex (OpenAlexClient)."""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.openalex import OpenAlexClient
from src.utils.errors import APIError, RateLimitError


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client():
    return OpenAlexClient(cache=None)


class TestOpenAlexClientConvertFormat:
    def test_convert_to_semantic_scholar_format_minimal(self, client):
        openalex = {
            "id": "https://openalex.org/W123",
            "display_name": "Test Paper",
            "doi": "https://doi.org/10.1234/foo",
            "abstract": None,
            "publication_year": 2020,
            "cited_by_count": 5,
            "referenced_works": ["W1", "W2"],
            "authorships": [],
            "primary_location": {},
        }
        out = client.convert_to_semantic_scholar_format(openalex)
        assert out["paperId"] == "W123"
        assert out["title"] == "Test Paper"
        assert out["year"] == 2020
        assert out["citationCount"] == 5
        assert out["referenceCount"] == 2
        assert out["externalIds"]["DOI"] == "10.1234/foo"
        assert out["externalIds"]["OpenAlex"] == "W123"

    def test_convert_to_semantic_scholar_format_with_authors(self, client):
        openalex = {
            "id": "https://openalex.org/W456",
            "display_name": "Paper",
            "doi": None,  # API may return None; implementation must handle
            "authorships": [
                {"author": {"id": "https://openalex.org/A1", "display_name": "Alice"}},
                {"author": {"id": "https://openalex.org/A2", "display_name": "Bob"}},
            ],
            "primary_location": {"source": {"display_name": "NeurIPS"}},
        }
        out = client.convert_to_semantic_scholar_format(openalex)
        assert len(out["authors"]) == 2
        assert out["authors"][0]["authorId"] == "A1"
        assert out["authors"][0]["name"] == "Alice"
        assert out["venue"] == "NeurIPS"


class TestOpenAlexClientGetPaper:
    def test_get_paper_returns_cached_when_hit(self, client):
        # Cache stores raw OpenAlex format; get_paper returns it as-is on hit (no conversion)
        cached = {"id": "https://openalex.org/W1", "display_name": "Cached"}
        client.cache = type("Cache", (), {"get": lambda self, k: cached})()
        client._make_request = AsyncMock()
        client._retry_with_backoff = AsyncMock()
        result = _run(client.get_paper("W1"))
        assert result["display_name"] == "Cached"
        assert "W1" in result["id"]
        client._make_request.assert_not_called()

    def test_get_paper_by_doi_returns_none_on_failure(self, client):
        client.cache = None
        client._retry_with_backoff = AsyncMock(side_effect=Exception("API error"))
        result = _run(client.get_paper_by_doi("10.1234/foo"))
        assert result is None

    def test_search_by_title_returns_empty_list_on_failure(self, client):
        client.cache = None
        client._retry_with_backoff = AsyncMock(side_effect=Exception("API error"))
        result = _run(client.search_by_title("Nonexistent"))
        assert result == []

    def test_get_citations_returns_empty_list_on_failure(self, client):
        client.cache = None
        client._retry_with_backoff = AsyncMock(side_effect=Exception("API error"))
        result = _run(client.get_citations("W123"))
        assert result == []


class TestOpenAlexHTTPTransport:
    """Tests using real HTTP path with mocked transport."""

    def test_get_paper_via_http_transport(self, client):
        """get_paper succeeds when transport returns OpenAlex JSON."""
        payload = {
            "id": "https://openalex.org/W99",
            "display_name": "HTTP Paper",
            "doi": "https://doi.org/10.99/bar",
            "authorships": [],
            "primary_location": {},
        }

        def _handler(request: httpx.Request) -> httpx.Response:
            assert "works" in str(request.url)
            return httpx.Response(200, json=payload)

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        result = _run(client.get_paper("W99"))
        assert result["paperId"] == "W99"
        assert result["title"] == "HTTP Paper"

    def test_get_paper_429_raises_rate_limit_error(self, client):
        client.cache = None

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        with pytest.raises(RateLimitError):
            _run(client.get_paper("W1"))

    def test_get_paper_by_doi_5xx_returns_none(self, client):
        """get_paper_by_doi catches exception and returns None."""
        client.cache = None

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        result = _run(client.get_paper_by_doi("10.1234/foo"))
        assert result is None

    def test_get_citations_limit_param(self, client):
        """get_citations passes limit (per-page) to API."""
        client.cache = None
        seen_params = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            seen_params["params"] = dict(request.url.params)
            return httpx.Response(200, json={"results": []})

        client.client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        _run(client.get_citations("W123", limit=50))
        assert seen_params["params"].get("per-page") == "50"
