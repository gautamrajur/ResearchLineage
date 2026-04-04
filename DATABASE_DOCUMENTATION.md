# Database Documentation

---

## ID Convention

| Term | Example | Where stored |
|------|---------|-------------|
| **arXiv ID** (user-facing) | `1706.03762` | `papers.arxiv_id` |
| **ARXIV lookup key** (entry point) | `ARXIV:1706.03762` | used to call `build_tree()` / `build_timeline()` |
| **S2 paper_id** (internal) | `204e3073870fae3d05bcbc2f6a8e263d9b72e776` | `papers.paper_id` (PK), all FK columns |

Both `build_tree()` and `build_timeline()` are **always called with an arXiv ID** in
the form `ARXIV:<number>`.  The Semantic Scholar API resolves this to its own internal
`paperId` on the first call.  All subsequent edge rows (`references`, `citations`,
`lineage`, `tree_nodes`) use the S2 `paper_id` as the FK.

The `arxiv_id` column enables the cache to be hit on future calls using the same
arXiv lookup key, without making an API call to resolve the ID again.

---

# Section 1 — Tree View

Documents exactly what happens when `build_tree("ARXIV:1706.03762")` is called,
what API calls are made, what gets saved, and what SQL replaces each call on cache hit.

---

## Full Flow

```
User calls build_tree("ARXIV:1706.03762")
          │
          ▼
┌─────────────────────┐
│  1. Fetch Target    │  resolve ARXIV ID -> S2 paper_id
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│  2. Fetch Ancestors │ <- recursive, depth-first
│     (references)    │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│  3. Fetch           │ <- recursive, depth-first, paginated
│     Descendants     │
│     (citations)     │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│  4. Return tree     │
│  { target,          │
│    ancestors:[],    │
│    descendants:[] } │
└─────────────────────┘
```

---

## Step 1 — Fetch Target Paper

Entry point is always an arXiv ID (`ARXIV:1706.03762`).
The cache is checked in two passes before making an API call.

### Cache Lookup (two-pass)
```sql
-- Pass 1: direct PK lookup (will miss on first call)
SELECT paper_id, title, year, citation_count, influential_citation_count
FROM   papers
WHERE  paper_id = 'ARXIV:1706.03762'

-- Pass 2: arxiv_id lookup (hits on all subsequent calls)
SELECT paper_id, title, year, citation_count, influential_citation_count
FROM   papers
WHERE  arxiv_id = '1706.03762'
```
If either query returns a row → skip API call entirely.

### API Call (on cache miss)
```
GET /paper/ARXIV:1706.03762
    fields: paperId, title, year, citationCount, influentialCitationCount
```

### API Response
```json
{
  "paperId":                   "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
  "title":                     "Attention Is All You Need",
  "year":                      2017,
  "citationCount":             90000,
  "influentialCitationCount":  12000
}
```

### Save to DB
```sql
-- paper_id = S2 internal ID, arxiv_id = bare arXiv number
INSERT OR IGNORE INTO papers
    (paper_id, arxiv_id, title, year, citation_count, influential_citation_count, fetched_at)
VALUES
    ('204e3073...', '1706.03762', 'Attention Is All You Need',
     2017, 90000, 12000, '2026-04-04T10:00:00')
```
`abstract`, `field_of_study`, `pdf_s3_uri`, `source_type` are NULL at this point —
filled in later by the LLM Explanation View pipeline.

All subsequent steps use the **S2 paper_id** (`204e3073...`) for API calls and FK joins.

---

## Step 2 — Fetch Ancestors (recursive per paper)

Runs once per paper node reached during ancestor traversal.
Repeats up to `max_depth` levels deep, up to `max_children` (default 3) per level.

### API Call
```
GET /paper/{paper_id}/references
    fields: citedPaper.paperId, citedPaper.title, citedPaper.year,
            citedPaper.citationCount, isInfluential, intents
    limit:  100
```

### API Response
```json
{
  "data": [
    {
      "isInfluential": true,
      "intents": ["methodology"],
      "citedPaper": {
        "paperId":       "def456",
        "title":         "Neural Machine Translation by Jointly Learning to Align",
        "year":          2015,
        "citationCount": 20000
      }
    },
    ...
  ]
}
```

### Filtering applied before saving
1. Keep refs where `"methodology" in intents`
2. If fewer than `max_children` found → also include `isInfluential = true`
3. Sort by `citationCount` descending, take top `max_children`
4. Recurse into each survivor

### Save to DB
One row per reference edge, plus a `papers` row for each cited paper, plus a `fetch_log` row
recording that this API call was made and how many results came back:
```sql
-- Save cited paper metadata (INSERT OR IGNORE — first batch wins for papers table)
INSERT OR IGNORE INTO papers
    (paper_id, title, year, citation_count, fetched_at)
VALUES
    ('def456', 'Neural Machine Translation...', 2015, 20000, '2026-04-04T10:00:00')

-- Save the edge, including cited_citation_count from THIS batch
-- This is the count used for ranking — not papers.citation_count (see Design Decisions)
INSERT OR IGNORE INTO references
    (paper_id, cited_paper_id, is_influential, intents, cited_citation_count, fetched_at)
VALUES
    ('abc123', 'def456', 1, '["methodology"]', 20000, '2026-04-04T10:00:00')

-- Always record the fetch — result_count=0 if API returned null/empty
-- year_start=0, year_end=0 are the sentinels for "no year window" (references have none)
INSERT OR REPLACE INTO fetch_log
    (paper_id, fetch_type, year_start, year_end, result_count, fetched_at)
VALUES
    ('abc123', 'references', 0, 0, 1, '2026-04-04T10:00:00')
```
All 100 refs from the API response are saved (not just the filtered top N),
so future queries with different `max_children` values still hit the cache.

If the API returns null or empty, `save_references` is still called with an empty list,
writing `result_count=0` to `fetch_log` so the call is never retried.

### Cache Hit — SQL replacing the API call
```sql
-- Check: have we ever fetched references for this paper (including empty results)?
SELECT COUNT(*) FROM fetch_log
WHERE  paper_id = 'abc123' AND fetch_type = 'references'
-- If > 0 → cache hit, skip GET /paper/abc123/references
-- (result_count=0 means the API returned nothing — references table will be empty for this paper)

-- Reproduce the filtered + sorted result (two-step fallback mirroring cold-run logic).
-- Step 1: methodology refs only
SELECT r.cited_paper_id, r.is_influential, r.intents, r.cited_citation_count, p.title, p.year
FROM   "references" r
JOIN   papers p ON p.paper_id = r.cited_paper_id
WHERE  r.paper_id = 'abc123' AND r.intents LIKE '%methodology%'

-- Step 2: if Step 1 count < max_children, also fetch influential (deduplicated in Python)
SELECT r.cited_paper_id, r.is_influential, r.intents, r.cited_citation_count, p.title, p.year
FROM   "references" r
JOIN   papers p ON p.paper_id = r.cited_paper_id
WHERE  r.paper_id = 'abc123' AND r.is_influential = 1

-- Step 3: sort combined list by cited_citation_count DESC, take top max_children in Python
-- ORDER BY r.cited_citation_count (edge-level), NOT p.citation_count.
-- Reason: papers.citation_count is from INSERT OR IGNORE — whichever batch
-- first inserted the paper. cited_citation_count is from THIS specific
-- /references batch, matching the count the cold run used for in-memory sort.
```

---

## Step 3 — Fetch Descendants (recursive per paper, paginated)

Runs once per paper node reached during descendant traversal.
Paginates in batches of 1,000 up to 9,000 at depth 0, 5,000 at deeper levels.
Year window: `paper_year + 1` to `paper_year + window_years` (default 3).

### API Call (repeated per offset until exhausted)
```
GET /paper/{paper_id}/citations
    fields: citingPaper.paperId, citingPaper.title, citingPaper.year,
            citingPaper.citationCount, intents, isInfluential
    limit:                1000
    offset:               0, 1000, 2000, ...
    publicationDateOrYear: 2018:2020   (year+1 : year+window_years)
```

### API Response (per batch)
```json
{
  "data": [
    {
      "isInfluential": true,
      "intents": ["methodology"],
      "citingPaper": {
        "paperId":       "ghi789",
        "title":         "BERT: Pre-training of Deep Bidirectional Transformers",
        "year":          2018,
        "citationCount": 60000
      }
    },
    ...
  ]
}
```

### Filtering applied before saving
1. Keep cites where `"methodology" in intents`
2. If fewer than `max_children` found → also include `isInfluential = true`
3. Sort by `citationCount` descending, take top `max_children`
4. Recurse into each survivor

### Save to DB
```sql
-- Save citing paper metadata (INSERT OR IGNORE — first batch wins for papers table)
INSERT OR IGNORE INTO papers
    (paper_id, title, year, citation_count, fetched_at)
VALUES
    ('ghi789', 'BERT: Pre-training...', 2018, 60000, '2026-04-04T10:00:00')

-- Save the edge, including citing_citation_count from THIS batch and the year window
-- citing_citation_count is the count used for ranking — not papers.citation_count
INSERT OR IGNORE INTO citations
    (paper_id, citing_paper_id, is_influential, intents,
     citing_citation_count, year_window_start, year_window_end, fetched_at)
VALUES
    ('abc123', 'ghi789', 1, '["methodology"]', 60000, 2018, 2020, '2026-04-04T10:00:00')

-- Always record the fetch — result_count=0 if API returned null/empty for this window
INSERT OR REPLACE INTO fetch_log
    (paper_id, fetch_type, year_start, year_end, result_count, fetched_at)
VALUES
    ('abc123', 'citations', 2018, 2020, 1, '2026-04-04T10:00:00')
```
All batched results are saved before filtering, so future calls with a wider
`window_years` can extend from the DB rather than re-fetching the full range.

If the API returns null or empty for a window, `save_citations` is still called with
an empty list, writing `result_count=0` to `fetch_log` so that window is never retried.

### Cache Hit — SQL replacing the API call
```sql
-- Check: have we fetched citations for this paper in this exact year window
-- (including windows that returned nothing)?
SELECT COUNT(*) FROM fetch_log
WHERE  paper_id    = 'abc123'
  AND  fetch_type  = 'citations'
  AND  year_start  = 2018
  AND  year_end    = 2020
-- If > 0 → cache hit, skip all GET /paper/abc123/citations pages
-- (result_count=0 means the API returned nothing — citations table will be empty for this window)

-- Reproduce the filtered + sorted result (two-step fallback mirroring cold-run logic).
-- Step 1: methodology cites within year window
SELECT c.citing_paper_id, c.is_influential, c.intents, c.citing_citation_count, p.title, p.year
FROM   citations c
JOIN   papers    p ON p.paper_id = c.citing_paper_id
WHERE  c.paper_id = 'abc123' AND p.year BETWEEN 2018 AND 2020
  AND  c.intents LIKE '%methodology%'

-- Step 2: if Step 1 count < max_children, also fetch influential (deduplicated in Python)
SELECT c.citing_paper_id, c.is_influential, c.intents, c.citing_citation_count, p.title, p.year
FROM   citations c
JOIN   papers    p ON p.paper_id = c.citing_paper_id
WHERE  c.paper_id = 'abc123' AND p.year BETWEEN 2018 AND 2020
  AND  c.is_influential = 1

-- Step 3: sort combined list by citing_citation_count DESC, take top max_children in Python
-- ORDER BY c.citing_citation_count (edge-level), NOT p.citation_count.
-- Reason: the same paper can appear in multiple API batches with different counts
-- (S2 counts are live/approximate). citing_citation_count is pinned to this specific
-- /citations batch — the same value the cold run used — guaranteeing identical top-N.
```

---

## Step 4 — Returned Tree Structure

```json
{
  "target": {
    "paperId":                  "abc123",
    "title":                    "Attention Is All You Need",
    "year":                     2017,
    "citationCount":            90000,
    "influentialCitationCount": 12000
  },
  "ancestors": [
    {
      "paper": { "paperId": "def456", "title": "...", "year": 2015, "citationCount": 20000 },
      "ancestors": [
        {
          "paper": { ... },
          "ancestors": []
        }
      ]
    }
  ],
  "descendants": [
    {
      "paper": { "paperId": "ghi789", "title": "...", "year": 2018, "citationCount": 60000 },
      "children": [
        {
          "paper": { ... },
          "children": []
        }
      ]
    }
  ]
}
```

### SQL to reconstruct the same structure from DB

**Target:**
```sql
SELECT paper_id, title, year, citation_count, influential_citation_count
FROM   papers
WHERE  paper_id = 'abc123'
```

**All ancestor edges (walk via references):**

Both steps below are executed in Python, not as a single SQL query.
Step 1 gets methodology refs; step 2 is only run if count < max_children.

```sql
-- Step 1: methodology refs
SELECT r.cited_paper_id, r.cited_citation_count, r.is_influential, r.intents, p.title, p.year
FROM   "references" r
JOIN   papers p ON p.paper_id = r.cited_paper_id
WHERE  r.paper_id = 'abc123'   -- or 'def456' for depth 2
  AND  r.intents LIKE '%methodology%'

-- Step 2 (only if step 1 count < max_children): influential refs not already in step 1
SELECT r.cited_paper_id, r.cited_citation_count, r.is_influential, r.intents, p.title, p.year
FROM   "references" r
JOIN   papers p ON p.paper_id = r.cited_paper_id
WHERE  r.paper_id = 'abc123'
  AND  r.is_influential = 1

-- Combine, deduplicate, sort by cited_citation_count DESC in Python, take top max_children
```

**All descendant edges (walk via citations):**

Same two-step pattern:

```sql
-- Step 1: methodology cites in year window
SELECT c.citing_paper_id, c.citing_citation_count, c.is_influential, c.intents, p.title, p.year
FROM   citations c
JOIN   papers    p ON p.paper_id = c.citing_paper_id
WHERE  c.paper_id = 'abc123'
  AND  p.year BETWEEN 2018 AND 2020
  AND  c.intents LIKE '%methodology%'

-- Step 2 (only if step 1 count < max_children): influential cites in year window
SELECT c.citing_paper_id, c.citing_citation_count, c.is_influential, c.intents, p.title, p.year
FROM   citations c
JOIN   papers    p ON p.paper_id = c.citing_paper_id
WHERE  c.paper_id = 'abc123'
  AND  p.year BETWEEN 2018 AND 2020
  AND  c.is_influential = 1

-- Combine, deduplicate, sort by citing_citation_count DESC in Python, take top max_children
```

The two-step Python fallback mirrors the cold-run filtering logic exactly —
ensuring warm-run top-N selection is identical to the cold run.

---

## Step 4 — Store Tree Run

Every paper node visited is recorded so the full tree can be reconstructed without any API calls.

### Save to DB
```sql
INSERT OR IGNORE INTO trees
    (tree_id, root_paper_id, generated_at, max_depth, max_children, window_years)
VALUES
    ('abc123_20260404_100000', 'abc123', '2026-04-04T10:00:00', 2, 5, 3)

-- One row per node (target + all ancestors + all descendants)
INSERT OR IGNORE INTO tree_nodes
    (tree_id, paper_id, node_type, depth, parent_paper_id)
VALUES
    ('abc123_20260404_100000', 'abc123', 'target',     0, NULL),
    ('abc123_20260404_100000', 'def456', 'ancestor',   1, 'abc123'),
    ('abc123_20260404_100000', 'ghi789', 'descendant', 1, 'abc123')
```

### Cache Hit — reconstruct full tree from DB
```sql
SELECT
    tn.node_type,
    tn.depth,
    tn.parent_paper_id,
    p.paper_id,
    p.title,
    p.year,
    p.citation_count,
    p.influential_citation_count
FROM   tree_nodes tn
JOIN   papers     p ON p.paper_id = tn.paper_id
WHERE  tn.tree_id = 'abc123_20260404_100000'
ORDER  BY tn.node_type, tn.depth
```

---

## User Feedback — Tree View

Feedback on whether a specific ancestor or descendant edge is correct.

### Save to DB
```sql
-- User says ancestor edge is wrong
INSERT INTO feedback
    (feedback_id, paper_id, related_paper_id, view_type, feedback_target,
     rating, comment, created_at)
VALUES
    ('uuid-001', 'abc123', 'def456', 'tree', 'tree_ancestor',
     -1, 'This is a background citation, not a methodology predecessor',
     '2026-04-04T11:00:00')

-- User says descendant edge is correct
INSERT INTO feedback
    (feedback_id, paper_id, related_paper_id, view_type, feedback_target,
     rating, comment, created_at)
VALUES
    ('uuid-002', 'abc123', 'ghi789', 'tree', 'tree_descendant',
     1, NULL, '2026-04-04T11:05:00')
```

### Query — read all feedback for a tree
```sql
SELECT
    f.feedback_target,
    f.rating,
    f.comment,
    f.created_at,
    p1.title  AS paper_title,
    p2.title  AS related_paper_title
FROM      feedback f
JOIN      papers   p1 ON p1.paper_id = f.paper_id
LEFT JOIN papers   p2 ON p2.paper_id = f.related_paper_id
WHERE     f.view_type = 'tree'
  AND     f.paper_id  = 'abc123'
ORDER BY  f.created_at DESC
```

---

## Tables Written Per Query

| Table | Written by | When |
|-------|-----------|------|
| `papers` | Step 1, 2, 3 | Every new paper encountered |
| `references` | Step 2 | After every `GET /references` call (skipped if result is null/empty) |
| `citations` | Step 3 | After every `GET /citations` batch (skipped if result is null/empty) |
| `fetch_log` | Step 2, 3 | **Always** after every `GET /references` or `GET /citations` call, including null/empty results — `result_count=0` marks a known-empty fetch |
| `trees` | Step 4 | Once per `build_tree()` call |
| `tree_nodes` | Step 4 | One row per paper node in the tree |
| `feedback` | User action | On every thumbs up / down submission |

---

## Cross-Tree Cache Reuse

The cache is **paper-centric, not tree-centric**. Every row written to `papers`,
`references`, `citations`, and `fetch_log` is keyed by `paper_id` — not by tree ID.
So any subsequent `build_tree()` call that reaches the same paper, from any root,
immediately gets a cache hit.

### What gets reused automatically

| Scenario | Cache hit |
|----------|-----------|
| Same paper is an ancestor in a new tree | `fetch_log` has `references` row → skip `/references` API call |
| Same paper is a descendant in a new tree with same year window | `fetch_log` has `citations` row for that window → skip all `/citations` pages |
| Same paper appears at any depth in any tree | `papers` row exists → skip paper metadata API call |
| Paper had no S2 references (result_count=0) | `fetch_log` row still present → never retried |

### What is NOT reused (requires a fresh API call)

| Scenario | Why |
|----------|-----|
| Paper was an ancestor before, now needs citations | `/citations` was never fetched — only `/references` was called when it was an ancestor |
| Paper was a descendant before, now needs references | `/references` was never fetched — only `/citations` was called when it was a descendant |
| Same paper in a different citation year window | `fetch_log` keys on `(paper_id, year_start, year_end)` — a different window is a cache miss |
| New papers reachable only via different traversal paths | Never visited before → no rows in any table |

### Practical consequence

After building the seed tree, a predecessor tree and a successor tree share a large
fraction of cached data:

**Predecessor tree** (rooted at seed's depth-1 ancestor):
- All ancestor nodes the predecessor shares with the seed: full cache hits
- Predecessor's own citations: fresh API call (it was never a descendant root)
- New papers only reachable via the predecessor's unique ancestors: fresh API calls

**Successor tree** (rooted at seed's depth-1 descendant):
- All descendant data the successor shares with the seed (same citation windows): cache hits
- Successor's own references: fresh API call (it was never an ancestor root)
- When traversing the successor's ancestor chain back through the seed paper:
  the seed paper's own direct ancestors (depth-2 from successor) are cache hits
  because they were fetched as the seed's ancestors in the original tree

### SQL to inspect cross-tree reuse

```sql
-- Papers that appear in more than one tree run
SELECT p.paper_id, p.title, COUNT(DISTINCT tn.tree_id) AS tree_count
FROM   papers p
JOIN   tree_nodes tn ON tn.paper_id = p.paper_id
GROUP  BY p.paper_id
HAVING tree_count > 1
ORDER  BY tree_count DESC;

-- Fetch log summary: how many papers have cached references vs citations
SELECT fetch_type,
       COUNT(*)                              AS total_fetches,
       SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) AS empty_fetches,
       SUM(result_count)                    AS total_rows_saved
FROM   fetch_log
GROUP  BY fetch_type;

-- Papers that returned empty references (result_count=0) — shown in UI as "no S2 data"
SELECT p.paper_id, p.title, fl.fetched_at
FROM   fetch_log fl
JOIN   papers    p ON p.paper_id = fl.paper_id
WHERE  fl.fetch_type = 'references' AND fl.result_count = 0
ORDER  BY fl.fetched_at DESC;
```

---

---

# Section 2 — LLM Explanation View

Documents exactly what happens when `build_timeline(paper_id)` is called,
what API and Gemini calls are made, what gets saved, and what SQL replaces each call on cache hit.

---

## Full Flow

```
User calls build_timeline(paper_id)
          │
          ▼
┌──────────────────────────┐
│  1. Fetch Target Paper   │  S2 API → papers table
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  2. Fetch PDF            │  arXiv download → S3 upload → papers.pdf_s3_uri
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  3. Fetch References     │  S2 API → references table
│     + Filter to          │
│     Methodology Candidates│
└──────────────────────────┘
          │
          ▼
┌──────────────────────────┐
│  4. Gemini — Select      │  Gemini API → lineage table
│     Predecessor +        │            → analysis table
│     Analyze Paper        │            → comparison table
│                          │            → secondary_influences table
└──────────────────────────┘
          │
          ▼
    predecessor_id
    becomes new
    paper_id → repeat
    from Step 1
          │
          ▼  (until is_foundational = true or max_depth reached)
┌──────────────────────────┐
│  5. Return chain         │
│  oldest → newest         │
│  with full analysis      │
└──────────────────────────┘
```

---

## Step 1 — Fetch Target Paper

### API Call
```
GET /paper/{paper_id}
    fields: paperId, title, year, abstract, citationCount,
            fieldsOfStudy, s2FieldsOfStudy, externalIds
```

### API Response
```json
{
  "paperId":        "abc123",
  "title":          "Attention Is All You Need",
  "year":           2017,
  "abstract":       "The dominant sequence transduction models...",
  "citationCount":  90000,
  "fieldsOfStudy":  ["Computer Science"],
  "s2FieldsOfStudy": [{ "category": "Computer Science", "source": "external" }],
  "externalIds":    { "ArXiv": "1706.03762" }
}
```

### Save to DB
```sql
INSERT OR IGNORE INTO papers
    (paper_id, arxiv_id, title, year, abstract, citation_count, field_of_study, fetched_at)
VALUES
    ('abc123', '1706.03762', 'Attention Is All You Need', 2017,
     'The dominant sequence...', 90000, 'Computer Science', '2026-04-04T10:00:00')
```

### Cache Hit — SQL replacing the API call
```sql
SELECT paper_id, arxiv_id, title, year, abstract, citation_count, field_of_study
FROM   papers
WHERE  paper_id = 'abc123'
```
If row exists → skip `GET /paper/{id}`.

---

## Step 2 — Fetch PDF and Upload to S3

### What happens
1. Use `arxiv_id` from Step 1 to download the PDF from arXiv
2. Upload PDF to S3 at `s3://bucket/papers/{paper_id}.pdf`
3. Store the S3 URI in the DB

No external API — this is an arXiv HTTP download + S3 PUT.

### Save to DB
```sql
UPDATE papers
SET    pdf_s3_uri  = 's3://bucket/papers/abc123.pdf',
       source_type = 'FULL_PDF'
WHERE  paper_id = 'abc123'
```
If no arXiv ID or download fails:
```sql
UPDATE papers
SET    source_type = 'ABSTRACT_ONLY'
WHERE  paper_id = 'abc123'
```

### Cache Hit — SQL replacing arXiv download + S3 upload
```sql
SELECT pdf_s3_uri, source_type
FROM   papers
WHERE  paper_id = 'abc123'
```
If `pdf_s3_uri IS NOT NULL` → read PDF directly from S3, skip arXiv + upload entirely.
If `source_type = 'ABSTRACT_ONLY'` → use `abstract` column, skip download attempt.

---

## Step 3 — Fetch References + Filter to Methodology Candidates

### API Call
```
GET /paper/{paper_id}/references
    fields: citedPaper.paperId, citedPaper.title, citedPaper.year,
            citedPaper.citationCount, isInfluential, intents
    limit:  100
```

### API Response
```json
{
  "data": [
    {
      "isInfluential": true,
      "intents": ["methodology"],
      "citedPaper": {
        "paperId":       "def456",
        "title":         "Neural Machine Translation by Jointly Learning...",
        "year":          2015,
        "citationCount": 20000
      }
    },
    ...
  ]
}
```

### Filtering applied (in `filter_methodology_references`)
1. Keep refs where `"methodology" in intents`
2. Fallback: also include `isInfluential = true` if too few methodology refs
3. Survivors become the candidate list passed to Gemini

### Save to DB
All 100 refs saved regardless of filtering, so future calls always hit the cache:
```sql
INSERT OR IGNORE INTO papers
    (paper_id, title, year, citation_count, fetched_at)
VALUES ('def456', 'Neural Machine Translation...', 2015, 20000, '2026-04-04T10:00:00')

INSERT OR IGNORE INTO references
    (paper_id, cited_paper_id, is_influential, intents, fetched_at)
VALUES ('abc123', 'def456', 1, '["methodology"]', '2026-04-04T10:00:00')
```

### Cache Hit — SQL replacing the API call
```sql
-- Check: have we fetched references for this paper?
SELECT COUNT(*) FROM references WHERE paper_id = 'abc123'
-- If > 0 → cache hit, skip GET /paper/abc123/references

-- Reproduce the filtered candidate list passed to Gemini:
SELECT
    r.cited_paper_id  AS paperId,
    p.title,
    p.year,
    p.citation_count  AS citationCount,
    r.is_influential  AS isInfluential,
    r.intents
FROM   references r
JOIN   papers     p ON p.paper_id = r.cited_paper_id
WHERE  r.paper_id = 'abc123'
  AND  (r.intents LIKE '%methodology%' OR r.is_influential = 1)
ORDER  BY p.citation_count DESC
```

---

## Step 4 — Gemini: Select Predecessor + Analyze Paper

### What happens
Gemini receives the target paper text (from S3 PDF) + all candidate texts and returns:
- Which candidate is the methodological predecessor
- Full analysis of the target paper
- Comparison of how it improved upon the predecessor

### Gemini Input (not saved — reconstructed from DB when needed)
- Target paper full text (read from S3 via `pdf_s3_uri`)
- Each candidate paper full text (read from S3 via their `pdf_s3_uri`)

### Gemini Output
```json
{
  "selected_predecessor_id": "def456",
  "selection_reasoning":     "The Bahdanau attention mechanism is the direct...",
  "secondary_influences": [
    { "paper_id": "xyz999", "contribution": "Encoder-decoder framework..." }
  ],
  "target_analysis": {
    "problem_addressed":      "RNNs struggle with long-range dependencies...",
    "core_method":            "Multi-head self-attention replaces recurrence...",
    "key_innovation":         "Parallelisable attention over entire sequence...",
    "limitations":            ["Quadratic memory with sequence length"],
    "breakthrough_level":     "revolutionary",
    "explanation_eli5":       "Instead of reading words one at a time...",
    "explanation_intuitive":  "A mechanism that lets every word attend...",
    "explanation_technical":  "Scaled dot-product attention with multiple heads..."
  },
  "comparison": {
    "what_was_improved":               "Replaced sequential recurrence with parallel attention",
    "how_it_was_improved":             "Self-attention computes dependencies in O(1) layers",
    "why_it_matters":                  "Enabled training on much larger datasets",
    "problem_solved_from_predecessor": "Eliminated vanishing gradient over long sequences",
    "remaining_limitations":           ["Quadratic cost limits very long contexts"]
  }
}
```

### Save to DB
```sql
-- Lineage: which paper is the predecessor + why
INSERT OR REPLACE INTO lineage
    (paper_id, predecessor_id, is_foundational, selection_reasoning)
VALUES ('abc123', 'def456', 0, 'The Bahdanau attention mechanism is the direct...')

-- Analysis: target_analysis block
INSERT OR REPLACE INTO analysis
    (paper_id, problem_addressed, core_method, key_innovation, limitations,
     breakthrough_level, explanation_eli5, explanation_intuitive,
     explanation_technical, analyzed_at)
VALUES
    ('abc123',
     'RNNs struggle with long-range dependencies...',
     'Multi-head self-attention replaces recurrence...',
     'Parallelisable attention over entire sequence...',
     '["Quadratic memory with sequence length"]',
     'revolutionary',
     'Instead of reading words one at a time...',
     'A mechanism that lets every word attend...',
     'Scaled dot-product attention with multiple heads...',
     '2026-04-04T10:00:00')

-- Comparison: how target improved predecessor
INSERT OR REPLACE INTO comparison
    (paper_id, predecessor_id, what_was_improved, how_it_was_improved,
     why_it_matters, problem_solved_from_predecessor, remaining_limitations)
VALUES
    ('abc123', 'def456',
     'Replaced sequential recurrence with parallel attention',
     'Self-attention computes dependencies in O(1) layers',
     'Enabled training on much larger datasets',
     'Eliminated vanishing gradient over long sequences',
     '["Quadratic cost limits very long contexts"]')

-- Secondary influences
INSERT OR IGNORE INTO secondary_influences
    (paper_id, influenced_by_id, contribution)
VALUES ('abc123', 'xyz999', 'Encoder-decoder framework...')
```

### Cache Hit — SQL replacing the Gemini call
```sql
-- Check: have we already run Gemini for this paper?
SELECT COUNT(*) FROM lineage WHERE paper_id = 'abc123'
-- If > 0 → cache hit, skip Gemini entirely

-- Reproduce the full Gemini output from DB:
SELECT
    l.predecessor_id       AS selected_predecessor_id,
    l.selection_reasoning,
    a.problem_addressed,
    a.core_method,
    a.key_innovation,
    a.limitations,
    a.breakthrough_level,
    a.explanation_eli5,
    a.explanation_intuitive,
    a.explanation_technical,
    c.what_was_improved,
    c.how_it_was_improved,
    c.why_it_matters,
    c.problem_solved_from_predecessor,
    c.remaining_limitations
FROM      lineage    l
JOIN      analysis   a ON a.paper_id = l.paper_id
LEFT JOIN comparison c ON c.paper_id = l.paper_id
WHERE     l.paper_id = 'abc123'
```

Secondary influences:
```sql
SELECT influenced_by_id AS paper_id, contribution
FROM   secondary_influences
WHERE  paper_id = 'abc123'
```

---

## Step 5 — Returned Chain Structure

The pipeline walks `paper → predecessor → predecessor → ...` until foundational,
then returns the chain reversed (oldest first):

```json
{
  "target_paper":  { "paperId": "abc123", "title": "Attention Is All You Need", "year": 2017 },
  "generated_at":  "2026-04-04 10:00:00",
  "total_papers":  4,
  "chain": [
    {
      "position": 1,
      "paper":    { "paperId": "lmn000", "title": "LSTM", "year": 1997, "abstract": "..." },
      "analysis": { "problem_addressed": "...", "key_innovation": "...", "breakthrough_level": "major", ... },
      "comparison_with_next": null,
      "secondary_influences": [],
      "source_type":     "FULL_PDF",
      "is_foundational": true
    },
    {
      "position": 2,
      "paper":    { "paperId": "jkl999", "title": "Seq2Seq", "year": 2014, "abstract": "..." },
      "analysis": { ... },
      "comparison_with_next": { "what_was_improved": "...", "how_it_was_improved": "...", ... },
      "secondary_influences": [{ "paper_id": "...", "contribution": "..." }],
      "source_type":     "FULL_PDF",
      "is_foundational": false
    },
    ...
  ]
}
```

### SQL to reconstruct the full chain from DB

```sql
-- Walk the chain from root paper backwards through lineage
-- Then reverse in application code for oldest-first ordering

-- Step A: get the full lineage path starting from queried paper
WITH RECURSIVE chain(paper_id, predecessor_id, depth) AS (
    SELECT paper_id, predecessor_id, 0
    FROM   lineage
    WHERE  paper_id = 'abc123'

    UNION ALL

    SELECT l.paper_id, l.predecessor_id, c.depth + 1
    FROM   lineage l
    JOIN   chain   c ON l.paper_id = c.predecessor_id
    WHERE  c.predecessor_id IS NOT NULL
)
-- Step B: join all data for each paper in the chain
SELECT
    c.depth,
    p.paper_id,
    p.title,
    p.year,
    p.abstract,
    p.pdf_s3_uri,
    p.source_type,
    a.problem_addressed,
    a.core_method,
    a.key_innovation,
    a.limitations,
    a.breakthrough_level,
    a.explanation_eli5,
    a.explanation_intuitive,
    a.explanation_technical,
    l.predecessor_id,
    l.is_foundational,
    l.selection_reasoning,
    cmp.what_was_improved,
    cmp.how_it_was_improved,
    cmp.why_it_matters,
    cmp.problem_solved_from_predecessor,
    cmp.remaining_limitations
FROM       chain      c
JOIN       papers     p   ON p.paper_id = c.paper_id
JOIN       lineage    l   ON l.paper_id = c.paper_id
LEFT JOIN  analysis   a   ON a.paper_id = c.paper_id
LEFT JOIN  comparison cmp ON cmp.paper_id = c.paper_id
ORDER BY   c.depth DESC   -- oldest ancestor first
```

Secondary influences per paper in chain:
```sql
SELECT paper_id, influenced_by_id, contribution
FROM   secondary_influences
WHERE  paper_id IN ('abc123', 'def456', 'jkl999', 'lmn000')
```

---

## Tables Written Per Query

| Table | Written by | When |
|-------|-----------|------|
| `papers` | Step 1 | Every paper fetched from S2 |
| `papers.pdf_s3_uri` | Step 2 | After PDF uploaded to S3 |
| `references` | Step 3 | After every `GET /references` call |
| `lineage` | Step 4 | After Gemini selects predecessor (includes `selection_reasoning`) |
| `analysis` | Step 4 | After Gemini analyzes target paper |
| `comparison` | Step 4 | After Gemini compares to predecessor |
| `secondary_influences` | Step 4 | After Gemini returns secondary list |
