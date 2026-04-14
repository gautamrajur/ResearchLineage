#!/usr/bin/env python3
"""
Sync user feedback from Cloud SQL → Elasticsearch for the Kibana Concept Drift dashboard.

Elasticsearch index:  rl-feedback
Index pattern:        rl-idx-feedback  (rl-feedback)

Each feedback record gets a derived `sentiment` field:
  rating > 0   →  "positive"  (thumbs up)
  rating <= 0  →  "negative"  (thumbs down)
  rating null  →  "unknown"

Run from project root:
    python scripts/sync_feedback_elasticsearch.py

Prerequisites:
  • Cloud SQL Auth Proxy running on CLOUD_SQL_HOST:CLOUD_SQL_PORT
  • Elasticsearch reachable at ELASTICSEARCH_HOST:ELASTICSEARCH_PORT
  • .env populated with ELASTICSEARCH_PASSWORD and CLOUD_SQL_* vars
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import requests
from sqlalchemy import create_engine, text

# ── Elasticsearch ─────────────────────────────────────────────────────────────
ES_HOST     = os.getenv("ELASTICSEARCH_HOST", "localhost")
ES_PORT     = os.getenv("ELASTICSEARCH_PORT", "9200")
ES_USER     = os.getenv("ELASTIC_USER", "elastic")
ES_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")
ES_BASE     = f"http://{ES_HOST}:{ES_PORT}"
ES_AUTH     = (ES_USER, ES_PASSWORD) if ES_PASSWORD else None

FEEDBACK_INDEX = "rl-feedback"

NOW = datetime.now(timezone.utc).isoformat()

# Only pin fields that need exact types; strings get dynamic text + .keyword mapping.
_MAPPING = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "rating":     {"type": "integer"},
        }
    }
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_index(index: str) -> None:
    r = requests.head(f"{ES_BASE}/{index}", auth=ES_AUTH)
    if r.status_code == 200:
        print(f"  {index} — already exists")
        return
    resp = requests.put(f"{ES_BASE}/{index}", json=_MAPPING, auth=ES_AUTH)
    resp.raise_for_status()
    print(f"  {index} — created")


def _bulk_index(index: str, docs: list[dict]) -> None:
    if not docs:
        print(f"  no docs to index → {index} (table is empty, will populate on next sync)")
        return
    lines = []
    for doc in docs:
        meta = {"index": {"_index": index, "_id": doc.pop("_id")}}
        lines.append(json.dumps(meta))
        lines.append(json.dumps(doc))
    body = "\n".join(lines) + "\n"
    resp = requests.post(
        f"{ES_BASE}/_bulk",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        auth=ES_AUTH,
    )
    resp.raise_for_status()
    result = resp.json()
    errors = [i for i in result.get("items", []) if i.get("index", {}).get("error")]
    if errors:
        print(f"  {len(errors)} bulk error(s): {errors[0]['index']['error']['reason']}")
    else:
        print(f"  indexed {len(docs)} docs → {index}")


def _parse_ts(created_at: str | None) -> str:
    """Best-effort parse of created_at text field → ISO timestamp."""
    if not created_at:
        return NOW
    try:
        from dateutil import parser as dtparser
        return dtparser.parse(created_at).isoformat()
    except Exception:
        return NOW


def _sentiment(rating: int | None) -> str:
    if rating is None:
        return "unknown"
    return "positive" if rating > 0 else "negative"


# ── Data loader ───────────────────────────────────────────────────────────────

def load_feedback() -> list[dict]:
    """Query Cloud SQL feedback table and return ES-ready documents."""
    host = os.getenv("CLOUD_SQL_HOST", "127.0.0.1")
    if host.lower() in ("localhost", "::1"):
        host = "127.0.0.1"
    db_url = (
        f"postgresql://{os.getenv('CLOUD_SQL_USER')}:{os.getenv('CLOUD_SQL_PASSWORD')}"
        f"@{host}:{os.getenv('CLOUD_SQL_PORT', '5433')}"
        f"/{os.getenv('CLOUD_SQL_DB', 'researchlineage')}"
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    query = text("""
        SELECT
            f.feedback_id,
            f.paper_id,
            COALESCE(p.title, f.paper_id) AS paper_label,
            f.related_paper_id,
            f.view_type,
            f.feedback_target,
            f.rating,
            f.comment,
            f.created_at
        FROM deployment_schema.feedback f
        LEFT JOIN deployment_schema.papers p ON p.paper_id = f.paper_id
        ORDER BY f.created_at DESC
    """)

    docs = []
    with engine.connect() as conn:
        for r in conn.execute(query).mappings():
            ts = _parse_ts(r["created_at"])
            docs.append({
                "_id":             r["feedback_id"],
                "@timestamp":      ts,
                "feedback_id":     r["feedback_id"],
                "paper_id":        r["paper_id"],
                "paper_label":     r["paper_label"],
                "related_paper_id":r["related_paper_id"],
                "view_type":       r["view_type"],
                "feedback_target": r["feedback_target"],
                "rating":          r["rating"],
                "sentiment":       _sentiment(r["rating"]),
                "comment":         r["comment"],
            })
    engine.dispose()
    print(f"  {len(docs)} feedback records loaded from Cloud SQL")
    return docs


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Concept Drift Feedback Sync → Elasticsearch ===\n")
    print("Loading feedback from Cloud SQL...")
    docs = load_feedback()
    _ensure_index(FEEDBACK_INDEX)
    _bulk_index(FEEDBACK_INDEX, docs)
    print("\nSync complete.")
    print("Open Kibana → [RL] Concept Drift — User Feedback to see the dashboard.")
    print("Re-run this script any time to refresh with new feedback.")


if __name__ == "__main__":
    from src.utils.logging import enable_script_logging
    enable_script_logging(__file__)
    main()
