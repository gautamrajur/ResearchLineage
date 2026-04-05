"""
common/s2_client.py
-------------------
Shared Semantic Scholar API client used by both views.

    pred_successor_view  →  get_paper(), get_references(), get_citations()
    evolution_view       →  same + filter_methodology_references(), normalize_paper_id()

Both views instantiate SemanticScholarClient directly.
"""

import re
import time
import requests
from typing import Dict, List, Optional

from .config import (
    S2_BASE_URL, S2_API_KEY,
    S2_REQUEST_TIMEOUT, S2_MAX_RETRIES,
    S2_RETRY_WAIT, S2_INTER_CALL_SLEEP,
    S2_PAPER_FIELDS_MINIMAL, S2_PAPER_FIELDS_FULL,
    S2_REFERENCE_FIELDS_MINIMAL, S2_REFERENCE_FIELDS_FULL,
    S2_CITATION_FIELDS,
    MAX_CANDIDATES,
    logger, log_event,
)


def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.0f} ms"


class SemanticScholarClient:
    """
    Wraps all Semantic Scholar /graph/v1 calls with:
      - Retry logic (constant 2 s wait on 429, up to S2_MAX_RETRIES)
      - Structured logging (every request + response)
      - 1.2 s inter-call sleep to stay within rate limits

    Usage:
        client = SemanticScholarClient()
        paper  = client.get_paper("ARXIV:1706.03762")
        refs   = client.get_references(paper["paperId"])
    """

    def __init__(self, api_key: Optional[str] = S2_API_KEY):
        self.base_url = S2_BASE_URL
        self._headers = {"x-api-key": api_key} if api_key else {}

    # ------------------------------------------------------------------
    # Core HTTP
    # ------------------------------------------------------------------

    def api_call(self, endpoint: str, params: Optional[Dict] = None,
                 max_retries: int = S2_MAX_RETRIES) -> Optional[Dict]:
        """
        Make one API call with rate-limit retry.

        Returns parsed JSON dict or None on unrecoverable failure.
        """
        endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{endpoint}"

        logger.info("  -> S2 REQUEST  %s  params=%s", endpoint, params)
        t0 = time.perf_counter()

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url, params=params,
                    headers=self._headers,
                    timeout=S2_REQUEST_TIMEOUT,
                )

                if response.status_code == 200:
                    data = response.json()
                    n = len(data.get("data", [])) if isinstance(data.get("data"), list) else "n/a"
                    logger.info("  <- S2 200  items=%s  elapsed=%s", n, _ms(t0))
                    logger.debug("  <- FULL  %s", data)
                    time.sleep(S2_INTER_CALL_SLEEP)
                    return data

                elif response.status_code == 429:
                    logger.warning(
                        "  <- S2 429 RATE LIMITED  attempt=%d/%d  waiting=%ds",
                        attempt + 1, max_retries, S2_RETRY_WAIT,
                    )
                    time.sleep(S2_RETRY_WAIT)
                    continue

                elif response.status_code == 404:
                    log_event("S2_NOT_FOUND", endpoint=endpoint)
                    logger.warning("  <- S2 404  %s", endpoint)
                    return None

                else:
                    logger.error(
                        "  <- S2 %d  body=%s", response.status_code, response.text[:300]
                    )
                    return None

            except Exception as exc:
                logger.error("  <- S2 REQUEST EXCEPTION  %s", exc)
                time.sleep(S2_RETRY_WAIT)
                continue

        logger.error("  <- S2 GAVE UP after %d retries  %s", max_retries, endpoint)
        return None

    # ------------------------------------------------------------------
    # Paper
    # ------------------------------------------------------------------

    def get_paper(self, paper_id: str, full_fields: bool = False) -> Optional[Dict]:
        """
        Fetch paper metadata.

        full_fields=False  → minimal set (pred_successor_view)
        full_fields=True   → extended set with abstract/tldr/authors (evolution_view)
        """
        paper_id = self.normalize_paper_id(paper_id)
        fields = S2_PAPER_FIELDS_FULL if full_fields else S2_PAPER_FIELDS_MINIMAL
        return self.api_call(f"paper/{paper_id}", {"fields": fields})

    # ------------------------------------------------------------------
    # References
    # ------------------------------------------------------------------

    def get_references(self, paper_id: str, full_fields: bool = False,
                       limit: int = 1000) -> List[Dict]:
        """
        Fetch all references for a paper.

        full_fields=False  → minimal (pred_successor_view)
        full_fields=True   → with contexts/abstract (evolution_view)

        Returns list of reference dicts (empty list on failure).
        """
        paper_id = self.normalize_paper_id(paper_id)
        fields = S2_REFERENCE_FIELDS_FULL if full_fields else S2_REFERENCE_FIELDS_MINIMAL
        result = self.api_call(
            f"paper/{paper_id}/references",
            {"fields": fields, "limit": limit},
        )
        if result and "data" in result and result["data"] is not None:
            return result["data"]
        return []

    # ------------------------------------------------------------------
    # Citations (paginated)
    # ------------------------------------------------------------------

    def get_citations_paginated(self, paper_id: str, start_year: int,
                                end_year: int, max_papers: int = 10000) -> List[Dict]:
        """
        Fetch citations for a paper within a year window, paginating until
        max_papers is reached or results are exhausted.

        Returns flat list of citing-paper dicts.
        """
        paper_id = self.normalize_paper_id(paper_id)
        all_cites: List[Dict] = []
        offset = 0
        limit  = 1000
        page   = 0

        while offset < max_papers and offset < 9000:
            page += 1
            t_page = time.perf_counter()
            params = {
                "fields": S2_CITATION_FIELDS,
                "limit": limit,
                "offset": offset,
                "publicationDateOrYear": f"{start_year}:{end_year}",
            }
            result = self.api_call(f"paper/{paper_id}/citations", params)

            if result is None or "data" not in result:
                logger.warning("  citations page=%d failed — stopping", page)
                break

            batch = result["data"]
            all_cites.extend(batch)
            logger.info(
                "  citations page=%d offset=%d batch=%d total=%d elapsed=%s",
                page, offset, len(batch), len(all_cites), _ms(t_page),
            )

            if len(batch) < limit:
                break

            offset += limit
            if offset < max_papers and offset < 9000:
                time.sleep(2)

        return all_cites

    # ------------------------------------------------------------------
    # Reference filtering (shared logic)
    # ------------------------------------------------------------------

    @staticmethod
    def filter_methodology_references(references: List[Dict],
                                      max_candidates: int = MAX_CANDIDATES) -> List[Dict]:
        """
        Filter raw references down to methodology candidates for Gemini.

        Steps (same logic used by both views):
          1. Keep papers with "methodology" in intents
          2. If not enough, add isInfluential papers (deduplicated)
          3. If still empty, fall back to top cited refs (sparse S2 annotation)
          4. Sort by citationCount DESC, take top max_candidates

        Returns list of dicts:
            {paper, is_influential, has_methodology, intents, contexts}
        """
        methodology: List[Dict] = []
        influential: List[Dict] = []

        for ref in references:
            cited = ref.get("citedPaper") or ref.get("paper") or {}
            if not cited.get("paperId") or not cited.get("title"):
                continue

            intents        = ref.get("intents") or []
            is_influential = ref.get("isInfluential", False)
            has_methodology = "methodology" in intents

            entry = {
                "paper":           cited,
                "is_influential":  is_influential,
                "has_methodology": has_methodology,
                "intents":         intents,
                "contexts":        ref.get("contexts") or [],
            }

            if has_methodology:
                methodology.append(entry)
            elif is_influential:
                influential.append(entry)

        # Fallback 1 — add influential when methodology count < max_candidates
        if len(methodology) < max_candidates:
            seen = {e["paper"]["paperId"] for e in methodology}
            for entry in influential:
                if entry["paper"]["paperId"] not in seen:
                    methodology.append(entry)

        # Fallback 2 — sparse annotations: take all refs regardless of intent
        if not methodology:
            for ref in references:
                cited = ref.get("citedPaper") or ref.get("paper") or {}
                if not cited.get("paperId") or not cited.get("title"):
                    continue
                methodology.append({
                    "paper":           cited,
                    "is_influential":  False,
                    "has_methodology": False,
                    "intents":         ref.get("intents") or [],
                    "contexts":        ref.get("contexts") or [],
                })

        methodology.sort(
            key=lambda c: c["paper"].get("citationCount") or 0,
            reverse=True,
        )
        return methodology[:max_candidates]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_paper_id(paper_id: str) -> str:
        """
        Normalise any paper ID format to what the S2 API accepts.

        "https://arxiv.org/abs/1706.03762"  → "ARXIV:1706.03762"
        "1706.03762"                         → "ARXIV:1706.03762"
        "ARXIV:1706.03762"                   → "ARXIV:1706.03762"
        "649def34f8be..."                    → "649def34f8be..."
        """
        pid = paper_id.strip()

        for pattern in [
            r"arxiv\.org/abs/(\d+\.\d+)",
            r"arxiv\.org/pdf/(\d+\.\d+)",
            r"arxiv\.org/html/(\d+\.\d+)",
        ]:
            m = re.search(pattern, pid)
            if m:
                return f"ARXIV:{m.group(1)}"

        if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", pid):
            return f"ARXIV:{pid}"

        if re.match(r"^[a-z-]+/\d+$", pid):
            return f"ARXIV:{pid}"

        return pid

    @staticmethod
    def get_arxiv_id(paper_data: Dict) -> Optional[str]:
        """Extract bare arXiv ID (e.g. '1706.03762') from paper data dict."""
        return (paper_data.get("externalIds") or {}).get("ArXiv")
