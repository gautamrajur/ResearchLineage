# Phase 3 — API Data Migration

Fetches live data from the Semantic Scholar Graph API for a seed paper, transforms it to SQL, and loads it into the PostgreSQL schema deployed in Phase 2.

---

## Directory Structure

```
migration/
├── endpoint_analysis.md     # Full Semantic Scholar API docs for each endpoint
├── mapping.md               # Field-by-field API → DB column mapping + data issues
├── README.md                # This file
└── scripts/
    ├── 01_fetch_and_analyze.py    # Fetch from Semantic Scholar → JSON files
    ├── 02_transform_to_sql.py     # JSON → SQL UPSERT scripts
    ├── insert_authors.sql         # Sample data (PDF schema, P1–P12)
    ├── insert_papers.sql
    ├── insert_paper_authors.sql
    ├── insert_citations.sql
    ├── insert_external_ids.sql
    ├── insert_citation_paths.sql
    └── insert_all.sql             # Combined — run this to load sample data
```

---

## Option A — Load Sample Data (Quick Start)

The `insert_all.sql` file contains the 12 papers, 8 authors, and 14 citation edges from the `Schema_MLOps.pdf`. Use this to verify the schema works before ingesting live data.

```bash
export DB_URL="postgresql://rl_user:<password>@<host>:5432/researchlineage"
psql "$DB_URL" --set ON_ERROR_STOP=1 -f scripts/insert_all.sql
```

**Expected counts after load:**

| Table | Rows |
|-------|------|
| authors | 8 |
| papers | 12 |
| paper_authors | 10 |
| citations | 14 |
| paper_external_ids | 7 |
| citation_paths | 2 |
| citation_path_nodes | 7 |

**Verify:**
```sql
SELECT 'authors'             AS tbl, COUNT(*) FROM authors             UNION ALL
SELECT 'papers',                     COUNT(*) FROM papers              UNION ALL
SELECT 'paper_authors',              COUNT(*) FROM paper_authors       UNION ALL
SELECT 'citations',                  COUNT(*) FROM citations           UNION ALL
SELECT 'paper_external_ids',         COUNT(*) FROM paper_external_ids  UNION ALL
SELECT 'citation_paths',             COUNT(*) FROM citation_paths      UNION ALL
SELECT 'citation_path_nodes',        COUNT(*) FROM citation_path_nodes;
```

---

## Option B — Ingest Live Semantic Scholar Data

### Prerequisites

```bash
pip install requests
# Optional but recommended — avoids rate limiting
export S2_API_KEY="your_api_key_here"
# Get one free at: https://www.semanticscholar.org/product/api
```

### Step 1 — Fetch

```bash
cd migration/scripts

python 01_fetch_and_analyze.py \
  --paper-id ARXIV:1706.03762 \
  --api-key "$S2_API_KEY" \
  --max-depth 2 \
  --max-children 5 \
  --window-years 3 \
  --output-dir ./output
```

This writes to `./output/`:
- `raw_target.json` — seed paper metadata
- `raw_all_papers.json` — all unique papers found
- `raw_all_authors.json` — all unique authors
- `raw_all_edges.json` — all citation edges
- `raw_references.json` — ancestor tree structure
- `raw_citations.json` — descendant tree structure

**Review** the JSON files before proceeding.

### Step 2 — Transform to SQL

```bash
python 02_transform_to_sql.py \
  --input-dir ./output \
  --output-dir ./sql_output \
  --max-depth 2
```

This generates `./sql_output/`:
- `insert_authors.sql`
- `insert_papers.sql`
- `insert_paper_authors.sql`
- `insert_citations.sql`
- `insert_external_ids.sql`
- `insert_citation_paths.sql`
- `insert_all.sql` (combined, wrapped in BEGIN/COMMIT)

**Review `insert_all.sql`** before running.

### Step 3 — Load

```bash
export DB_URL="postgresql://rl_user:<password>@<host>:5432/researchlineage"
psql "$DB_URL" --set ON_ERROR_STOP=1 -f ./sql_output/insert_all.sql
```

---

## FK Dependency Order

Insert data in this order or use `insert_all.sql` which handles it:

```
1. authors
2. papers
3. paper_authors         (FK → papers, authors)
4. citations             (FK → papers × 2)
5. paper_external_ids    (FK → papers)
6. citation_paths        (FK → papers)
7. citation_path_nodes   (FK → citation_paths, papers)
```

---

## Not Covered by Semantic Scholar API

These tables must be populated separately:

| Table | Method |
|-------|--------|
| `paper_embeddings` | Call OpenAI/Cohere embeddings API on `abstract` or `title` |
| `paper_sections` | Download PDF (from `openAccessPdf.url`) → parse with PyMuPDF → embed sections |

See `mapping.md` for details on each field.

---

## Rollback

All inserts use `ON CONFLICT DO UPDATE` (upsert). To remove all data:

```sql
-- Truncate in reverse FK order
TRUNCATE citation_path_nodes, citation_paths,
         paper_external_ids, paper_embeddings, paper_sections,
         citations, paper_authors, papers, authors
CASCADE;
```

Or re-run `rollback_schema.sql` from Phase 2 to drop all tables.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `HTTP 429` from Semantic Scholar | Script retries automatically. Get an API key for higher limits. |
| `FK violation on citations` | A cited/citing paper was not fetched — increase `--max-children` or add paper manually |
| `CHECK constraint violation on year` | Paper has NULL year (pre-print) — script defaults to NULL which is allowed |
| `vector dimension mismatch` | embedding_dimension in `paper_embeddings` must match the pgvector column (1536) |
| `duplicate key value violates unique constraint` | Normal — `ON CONFLICT DO UPDATE` handles it. Check `ON_ERROR_STOP` isn't triggering on something else |
