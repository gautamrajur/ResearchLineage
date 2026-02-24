"""Top-level shared data factory helpers used across unit and integration tests."""


def make_paper(
    paper_id="p1",
    title="Test Paper",
    year=2020,
    citation_count=500,
    abstract="Test abstract.",
    venue="NeurIPS",
    authors=None,
    arxiv_id="1234.5678",
):
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "citationCount": citation_count,
        "influentialCitationCount": 50,
        "referenceCount": 20,
        "abstract": abstract,
        "venue": venue,
        "authors": authors or [{"authorId": "a1", "name": "Alice Smith"}],
        "externalIds": {"ArXiv": arxiv_id},
        "url": f"https://example.com/{paper_id}",
    }


def make_ref(from_id="p1", to_id="p2", intents=None, is_influential=True):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": is_influential,
        "contexts": ["We build upon this work."],
        "intents": intents or ["methodology"],
        "direction": "backward",
    }


def make_cit(from_id="p3", to_id="p1", intents=None):
    return {
        "fromPaperId": from_id,
        "toPaperId": to_id,
        "isInfluential": False,
        "contexts": [],
        "intents": intents or ["methodology"],
        "direction": "forward",
    }
"""
Pytest configuration and shared fixtures.

- Adds project root to sys.path so imports like 'from src.utils.id_mapper import IDMapper' work.
- Mocks google.cloud.storage so tests can import src.tasks.pdf_fetcher without the real GCS package.
- Adds terminal formatting for clear visual output when running tests.
"""
import os
import sys
from unittest.mock import MagicMock

# Project root (directory containing src/, tests/, temp/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Allow importing pdf_fetcher (which pulls in gcs_client -> google.cloud.storage) without installing google-cloud-storage
sys.modules["google.cloud.storage"] = MagicMock(Client=MagicMock())

# Allow importing api clients (which pull in redis_client -> redis) without requiring redis in test env
_redis_mock = MagicMock()
sys.modules["redis"] = _redis_mock


# ─── Shared test data fixtures ───────────────────────────────────────────

import pytest


@pytest.fixture
def sample_paper():
    """Standard paper fixture for tests."""
    return {
        "paperId": "test123",
        "title": "Test Paper Title",
        "abstract": "This is a test abstract.",
        "year": 2020,
        "citationCount": 100,
        "influentialCitationCount": 10,
        "referenceCount": 50,
        "authors": [{"authorId": "a1", "name": "Test Author"}],
        "externalIds": {"DOI": "10.1234/test", "ArXiv": "2001.00001"},
        "venue": "Test Conference",
        "url": "https://example.com/paper",
    }


@pytest.fixture
def sample_reference():
    """Standard reference fixture."""
    return {
        "fromPaperId": "paper1",
        "toPaperId": "paper2",
        "isInfluential": False,
        "contexts": ["In this work..."],
        "intents": ["methodology"],
    }


@pytest.fixture
def sample_citation():
    """Standard citation fixture."""
    return {
        "fromPaperId": "citing_paper",
        "toPaperId": "cited_paper",
        "isInfluential": True,
        "contexts": [],
        "intents": [],
    }


# ─── Terminal formatting for visual clarity ───────────────────────────────

BANNER = "=" * 60
SECTION = "-" * 60


def pytest_configure(config):
    """Print banner at start of test run."""
    if config.getoption("verbose", 0) >= 0:
        print(f"\n{BANNER}")
        print("  ResearchLineage — Test Run")
        print(f"{BANNER}\n")


def pytest_sessionstart(session):
    """Print section when session starts."""
    print("  Session started.")
    print(f"{SECTION}\n")


def pytest_sessionfinish(session, exitstatus):
    """Print summary and banner at end of run."""
    print(f"\n{SECTION}")
    if exitstatus == 0:
        print("  Result: ALL PASSED")
    else:
        print("  Result: FAILED (see above)")
    print(f"{BANNER}\n")
