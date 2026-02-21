# seed_picker.py
import argparse
import json
import random
import time
from typing import Dict, List, Optional
import os
import requests

from config import S2_BASE_URL, S2_API_KEY, S2_REQUEST_TIMEOUT, VERBOSE


BULK_SEARCH_ENDPOINT = "paper/search/bulk"

DEFAULT_DOMAINS = [
    "Computer Science",
    "Physics",
    "Mathematics",
    "Statistics",
    "Engineering",
    "Biology",
    "Economics"
]


# ==========================================
# API Call
# ==========================================

def _api_get(endpoint: str, params: Dict) -> Optional[Dict]:
    url = f"{S2_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    try:
        r = requests.get(url, params=params, headers=headers, timeout=S2_REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if VERBOSE:
            print(f"❌ S2 error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        if VERBOSE:
            print(f"❌ Request failed: {e}")
        return None


# ==========================================
# Bulk Search
# ==========================================

def bulk_search_top_cited(
    field_of_study: str,
    pool_size: int,
    query: str,
    min_citations: int,
) -> List[Dict]:

    fields = "paperId,title,year,citationCount,externalIds"

    results = []
    token = None

    while len(results) < pool_size:
        limit = min(1000, pool_size - len(results))

        params = {
            "query": query,
            "fields": fields,
            "limit": limit,
            "sort": "citationCount:desc",
            "minCitationCount": min_citations,
            "fieldsOfStudy": field_of_study,
            "year": "2000-",
            "openAccessPdf": "",
        }

        if token:
            params["token"] = token

        data = _api_get(BULK_SEARCH_ENDPOINT, params)
        if not data:
            break

        batch = data.get("data") or []
        if not batch:
            break

        results.extend(batch)
        token = data.get("token")

        if not token:
            break

        time.sleep(1.0)

    return results[:pool_size]


# ==========================================
# Build Seeds
# ==========================================

def build_seeds(
    n_total: int,
    domains: List[str],
    per_domain_pool: int,
    seed: int,
    min_citations: int,
    query: str,
) -> List[Dict]:

    random.seed(seed)
    seeds = []
    seen_ids = set()

    per_domain_target = max(1, n_total // len(domains))

    for domain in domains:
        if VERBOSE:
            print(f"\n🔎 Domain: {domain} | building pool of {per_domain_pool}")

        pool = bulk_search_top_cited(
            field_of_study=domain,
            pool_size=per_domain_pool,
            query=query,
            min_citations=min_citations,
        )

        if VERBOSE:
            print(f"  ✅ Pool fetched: {len(pool)} papers")

        random.shuffle(pool)

        count = 0
        for p in pool:
            pid = p.get("paperId")
            external_ids = p.get("externalIds") or {}

            # 🔥 ONLY keep papers with ArXiv ID
            if not pid or pid in seen_ids:
                continue

            if "ArXiv" not in external_ids:
                continue

            seeds.append({
                "paperId": pid,
                "title": p.get("title"),
                "year": p.get("year"),
                "citationCount": p.get("citationCount"),
                "domain": domain,
                "arxiv_id": external_ids.get("ArXiv"),
            })

            seen_ids.add(pid)
            count += 1

            if count >= per_domain_target:
                break

        if VERBOSE:
            print(f"  🎯 Sampled {count} ArXiv seeds from {domain}")

        if len(seeds) >= n_total:
            break

    return seeds[:n_total]


# ==========================================
# CLI
# ==========================================



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--domains", type=str, default=",".join(DEFAULT_DOMAINS))
    parser.add_argument("--per-domain-pool", type=int, default=800)
    parser.add_argument("--min-citations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--query",
        type=str,
        default="model | method | study | analysis",
    )
    parser.add_argument("--out", type=str, default="inputs/seeds.json")

    args = parser.parse_args()

    # ADD THESE TWO LINES:
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]

    seeds = build_seeds(
        n_total=args.n,
        domains=domains,
        per_domain_pool=args.per_domain_pool,
        seed=args.seed,
        min_citations=args.min_citations,
        query=args.query,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(seeds, f, indent=2)

    print(f"\n✅ Wrote {len(seeds)} ArXiv seeds to {args.out}")


if __name__ == "__main__":
    main()