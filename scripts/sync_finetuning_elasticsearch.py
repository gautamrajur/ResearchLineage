#!/usr/bin/env python3
"""
Sync fine-tuning data to Elasticsearch for the Kibana Data Drift dashboard.

Two Elasticsearch indices are maintained:
  rl-finetuning-snapshot  —  GCS train_metadata_fixed.jsonl  (static training snapshot)
  rl-finetuning-live      —  Current Cloud SQL lineage state  (always full-refreshed)

Run from project root:
    python scripts/sync_finetuning_elasticsearch.py

Prerequisites:
  • Cloud SQL Auth Proxy running on CLOUD_SQL_HOST:CLOUD_SQL_PORT
  • Elasticsearch reachable at ELASTICSEARCH_HOST:ELASTICSEARCH_PORT
  • .env populated with ELASTICSEARCH_PASSWORD and CLOUD_SQL_* vars
"""

import json
import os
import subprocess
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

SNAPSHOT_INDEX = "rl-finetuning-snapshot"
LIVE_INDEX     = "rl-finetuning-live"

GCS_URI = "gs://researchlineage-gcs/fine-tuning-artifacts//latest/train_metadata_fixed.jsonl"

NOW = datetime.now(timezone.utc).isoformat()

# ── ES index mappings ─────────────────────────────────────────────────────────
# Use dynamic mapping so string fields get automatic text + .keyword sub-fields,
# which is what Kibana aggregation-based visualizations expect (e.g. source_type.keyword).
# Only pin the date and numeric fields that need exact types.
_MAPPING = {
    "mappings": {
        "properties": {
            "@timestamp":          {"type": "date"},
            "year":                {"type": "integer"},
            "citation_count":      {"type": "long"},
            "depth":               {"type": "integer"},
            "candidate_list_size": {"type": "integer"},
            "is_terminal":         {"type": "boolean"},
            "domain_was_changed":  {"type": "boolean"},
        }
    }
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_index(index: str) -> None:
    """Create ES index with mappings if it does not exist yet."""
    r = requests.head(f"{ES_BASE}/{index}", auth=ES_AUTH)
    if r.status_code == 200:
        print(f"  {index} — already exists")
        return
    resp = requests.put(f"{ES_BASE}/{index}", json=_MAPPING, auth=ES_AUTH)
    resp.raise_for_status()
    print(f"  {index} — created")


def _bulk_index(index: str, docs: list[dict]) -> None:
    """Upsert documents into ES via the bulk API. Uses doc_id for idempotency."""
    if not docs:
        print(f"  no docs to index → {index} (skipped)")
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


def _map_source_type(text_availability: str | None) -> str:
    if not text_availability:
        return "UNKNOWN"
    ta = text_availability.lower()
    if "full" in ta:
        return "FULL_TEXT"
    if "abstract" in ta:
        return "ABSTRACT_ONLY"
    return "UNKNOWN"


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_snapshot() -> list[dict]:
    """Download GCS JSONL and return ES-ready documents."""
    print(f"  downloading {GCS_URI}")
    result = subprocess.run(
        ["gsutil", "cat", GCS_URI],
        capture_output=True, text=True, check=True,
    )
    docs = []
    for line in result.stdout.strip().splitlines():
        r    = json.loads(line)
        dc   = r.get("domain_classification", {})
        idx  = r["sample_index"]
        docs.append({
            "_id":                 f"snapshot_{idx}",
            "@timestamp":          NOW,
            "data_source":         "snapshot",
            "paper_id":            r["seed_paper_id"],
            "year":                r.get("seed_paper_year"),
            "citation_count":      r.get("seed_citation_count"),
            "depth":               r.get("depth"),
            "source_type":         r.get("source_type", "UNKNOWN"),
            "field_of_study":      dc.get("gemini_field"),
            "is_terminal":         r.get("is_terminal", False),
            "candidate_list_size": r.get("candidate_list_size", 0),
            "model_used":          r.get("model_used"),
            "domain_was_changed":  dc.get("was_changed", False),
        })
    print(f"  {len(docs)} records parsed from GCS")
    return docs


def load_live() -> list[dict]:
    """Query Cloud SQL lineage data and return ES-ready documents."""
    host = os.getenv("CLOUD_SQL_HOST", "127.0.0.1")
    # Force IPv4 — Cloud SQL proxy binds to 127.0.0.1, not ::1
    if host.lower() in ("localhost", "::1"):
        host = "127.0.0.1"
    db_url = (
        f"postgresql://{os.getenv('CLOUD_SQL_USER')}:{os.getenv('CLOUD_SQL_PASSWORD')}"
        f"@{host}:{os.getenv('CLOUD_SQL_PORT', '5433')}"
        f"/{os.getenv('CLOUD_SQL_DB', 'researchlineage')}"
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    # LEFT JOIN lineage_papers — captures all papers even when lineage_papers is empty.
    # depth/direction/is_terminal will be null until lineage data is populated.
    query = text("""
        SELECT
            p.paperid                AS paper_id,
            p.year,
            p.citationcount          AS citation_count,
            p.text_availability,
            p.first_queried_at,
            lp.position_in_chain     AS depth,
            lp.target_paperid        AS target_paper_id,
            lp.direction,
            CASE
                WHEN lp.lineage_paper_id IS NULL THEN NULL
                WHEN pc.connection_id    IS NULL THEN true
                ELSE false
            END                      AS is_terminal
        FROM  papers p
        LEFT  JOIN lineage_papers    lp  ON  p.paperid = lp.paperid
        LEFT  JOIN paper_connections pc  ON  lp.lineage_paper_id = pc.from_lineage_paper_id
    """)

    docs = []
    with engine.connect() as conn:
        for r in conn.execute(query).mappings():
            # @timestamp = first_queried_at so the growth-over-time chart reflects
            # when each paper actually entered the DB, not the sync time.
            fqa     = r["first_queried_at"]
            ts      = fqa.isoformat() if fqa else NOW
            is_term = r["is_terminal"]
            docs.append({
                "_id":             f"live_{r['paper_id']}",
                "@timestamp":      ts,
                "data_source":     "live",
                "paper_id":        r["paper_id"],
                "year":            r["year"],
                "citation_count":  r["citation_count"],
                "depth":           r["depth"],
                "source_type":     _map_source_type(r["text_availability"]),
                "field_of_study":  None,
                "is_terminal":     bool(is_term) if is_term is not None else None,
                "target_paper_id": r["target_paper_id"],
                "direction":       r["direction"],
            })
    engine.dispose()
    print(f"  {len(docs)} records loaded from Cloud SQL")
    return docs


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Fine-Tuning Data Drift Sync → Elasticsearch ===\n")

    print("Step 1 — Snapshot (GCS):")
    snap_docs = load_snapshot()
    _ensure_index(SNAPSHOT_INDEX)
    _bulk_index(SNAPSHOT_INDEX, snap_docs)

    print("\nStep 2 — Live (Cloud SQL):")
    live_docs = load_live()
    _ensure_index(LIVE_INDEX)
    _bulk_index(LIVE_INDEX, live_docs)

    print("\nSync complete.")
    print("Open Kibana → [RL] Fine-Tuning Data Drift to see the comparison.")
    print("Re-run this script any time to refresh the live index.")


if __name__ == "__main__":
    from src.utils.logging import enable_script_logging
    enable_script_logging(__file__)
    main()
