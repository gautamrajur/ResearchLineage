"""
Unit tests for src.utils.id_mapper (pytest).

Tests extract_doi, extract_arxiv_id, get_openalex_id with Semantic Scholar,
OpenAlex, missing/empty inputs, and aggressive edge cases.
"""
import pytest
from src.utils.id_mapper import IDMapper


def test_extract_doi():
    """extract_doi: Semantic Scholar, OpenAlex, missing/empty."""
    assert IDMapper.extract_doi({"externalIds": {"DOI": "10.1234/foo"}}) == "10.1234/foo"
    assert IDMapper.extract_doi({"doi": "https://doi.org/10.5678/bar"}) == "10.5678/bar"
    assert IDMapper.extract_doi({"doi": "10.5678/baz"}) == "10.5678/baz"
    assert IDMapper.extract_doi({}) is None
    assert IDMapper.extract_doi({"externalIds": {}}) is None
    assert IDMapper.extract_doi({"externalIds": {"ArXiv": "1234.5678"}}) is None


def test_extract_doi_edge_cases():
    """extract_doi: aggressive edge cases."""
    # externalIds explicitly None -> skip S2 branch, then check doi
    assert IDMapper.extract_doi({"externalIds": None}) is None
    # doi empty string -> treated as falsy, return None
    assert IDMapper.extract_doi({"doi": ""}) is None
    # DOI key present but empty string -> falsy, impl returns None
    assert IDMapper.extract_doi({"externalIds": {"DOI": ""}}) is None
    # doi with only prefix (edge URL)
    assert IDMapper.extract_doi({"doi": "https://doi.org/10.0"}) == "10.0"
    # Both externalIds and doi present: S2 takes precedence
    assert IDMapper.extract_doi({
        "externalIds": {"DOI": "10.s2/first"},
        "doi": "https://doi.org/10.openalex/second",
    }) == "10.s2/first"
    # doi is None (key exists, value None) -> falsy, return None
    assert IDMapper.extract_doi({"doi": None}) is None


def test_extract_arxiv_id():
    """extract_arxiv_id: Semantic Scholar, OpenAlex, missing/empty."""
    assert IDMapper.extract_arxiv_id({"externalIds": {"ArXiv": "1706.03762"}}) == "1706.03762"
    assert IDMapper.extract_arxiv_id({"ids": {"arxiv": ["1706.03762"]}}) == "1706.03762"
    assert IDMapper.extract_arxiv_id({}) is None
    assert IDMapper.extract_arxiv_id({"externalIds": {}}) is None
    assert IDMapper.extract_arxiv_id({"externalIds": {"DOI": "10.1/ab"}}) is None


def test_extract_arxiv_id_edge_cases():
    """extract_arxiv_id: aggressive edge cases."""
    # OpenAlex: empty arxiv list -> no identifier, return None
    assert IDMapper.extract_arxiv_id({"ids": {"arxiv": []}}) is None
    # OpenAlex: ids missing -> .get("ids", {}) then .get("arxiv", []) -> None
    assert IDMapper.extract_arxiv_id({"ids": {}}) is None
    # OpenAlex: ids.arxiv missing
    assert IDMapper.extract_arxiv_id({"ids": {"other": []}}) is None
    # OpenAlex: multiple arxiv IDs -> implementation returns first
    assert IDMapper.extract_arxiv_id({"ids": {"arxiv": ["1706.03762", "1234.5678"]}}) == "1706.03762"
    # ArXiv key present but empty string -> falsy, impl returns None
    assert IDMapper.extract_arxiv_id({"externalIds": {"ArXiv": ""}}) is None
    # externalIds explicitly None -> skip S2 branch, then ids
    assert IDMapper.extract_arxiv_id({"externalIds": None, "ids": {"arxiv": ["99.99"]}}) == "99.99"


def test_get_openalex_id():
    """get_openalex_id: from id URL, from externalIds, missing."""
    assert IDMapper.get_openalex_id({"id": "https://openalex.org/W123"}) == "W123"
    assert IDMapper.get_openalex_id({"externalIds": {"OpenAlex": "W456"}}) == "W456"
    assert IDMapper.get_openalex_id({}) is None
    assert IDMapper.get_openalex_id({"id": "https://other.org/x"}) is None


def test_get_openalex_id_edge_cases():
    """get_openalex_id: aggressive edge cases; invalid/missing id returns None."""
    # Trailing slash -> normalized to W123; root URL -> no ID segment, return None
    assert IDMapper.get_openalex_id({"id": "https://openalex.org/W123/"}) == "W123"
    assert IDMapper.get_openalex_id({"id": "https://openalex.org/"}) is None
    # OpenAlex key present but empty string -> falsy, return None
    assert IDMapper.get_openalex_id({"externalIds": {"OpenAlex": ""}}) is None
    # externalIds None -> skip OpenAlex branch
    assert IDMapper.get_openalex_id({"externalIds": None}) is None
    # Invalid id: None or non-string -> return None (no AttributeError)
    assert IDMapper.get_openalex_id({"id": None}) is None
    assert IDMapper.get_openalex_id({"id": 12345}) is None
