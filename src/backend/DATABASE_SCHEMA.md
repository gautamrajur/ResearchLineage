# Database Schema — Research Lineage Cache

Single SQLite file (`lineage_cache.db`) caching all Semantic Scholar API responses,
S3 PDF paths, and Gemini analysis outputs. Both `pipeline.py` and `tree_builder.py`
read from and write to this database before making any external call.

---

## Entry Point — arXiv ID

Both `build_tree()` and `build_timeline()` are always triggered with an **arXiv ID**
(e.g. `ARXIV:1706.03762`).  On the very first call the Semantic Scholar API resolves
this to its own internal `paperId` (a 40-char hex string such as
`204e3073870fae3d05bcbc2f6a8e263d9b72e776`).  From that point forward all internal
joins, foreign keys, and edge rows use the **S2 paper_id**.

The `arxiv_id` column exists so future lookups with the same arXiv reference can hit
the cache without making an API call:

```
User passes "ARXIV:1706.03762"
        │
        ▼
cache.get_paper("ARXIV:1706.03762")
        │
        ├── try WHERE paper_id = 'ARXIV:1706.03762'  → miss (no such row)
        └── try WHERE arxiv_id = '1706.03762'         → HIT  (row stored on first call)
                │
                └── returns row with paper_id = '204e3073...'
```

---

## Tables

### `papers`
One row per paper. Populated by both pipelines. Columns from `tree_builder.py` and
`pipeline.py` are merged here — columns not yet fetched are NULL.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `paper_id` | TEXT PK | both | **Semantic Scholar internal ID** (40-char hex). Never the arXiv ID. |
| `arxiv_id` | TEXT | both | Bare arXiv number e.g. `1706.03762`. Populated by tree_builder on first call via `ARXIV:` lookup, and by pipeline from `externalIds.ArXiv`. Used as a secondary lookup key. |
| `title` | TEXT | both | |
| `year` | INT | both | |
| `abstract` | TEXT | pipeline | |
| `citation_count` | INT | both | |
| `influential_citation_count` | INT | tree | From `influentialCitationCount` field |
| `field_of_study` | TEXT | pipeline | Primary field from S2 `fieldsOfStudy` |
| `pdf_s3_uri` | TEXT | pipeline | S3 path to the paper PDF e.g. `s3://bucket/papers/{paper_id}.pdf` |
| `source_type` | TEXT | pipeline | `FULL_PDF` or `ABSTRACT_ONLY` — whether a PDF was found |
| `fetched_at` | TEXT | both | ISO timestamp of last S2 fetch |

**Cache hit (by S2 ID):** `SELECT ... WHERE paper_id = ?` → row exists → skip API call.
**Cache hit (by arXiv ID):** `SELECT ... WHERE arxiv_id = ?` → row exists → skip API call.
**PDF cache hit:** `pdf_s3_uri IS NOT NULL` → skip arXiv fetch and S3 upload, read PDF directly from S3.

---

### `references`
Papers that paper X cites (ancestors / older work). Each row is always read and
written with `paper_id = X` — the paper doing the citing.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT FK → papers | The paper that cites |
| `cited_paper_id` | TEXT FK → papers | The paper being cited |
| `is_influential` | INT | 1 if S2 marked it influential |
| `intents` | TEXT | JSON array e.g. `["methodology", "background"]` |
| `cited_citation_count` | INT | `citationCount` from this `/references` API batch. **Used for ORDER BY on cache read** so warm-run sort order matches cold-run in-memory sort. |
| `fetched_at` | TEXT | ISO timestamp |

Primary key: `(paper_id, cited_paper_id)`

**Cache hit:** any row exists where `paper_id = X` → skip `GET /paper/X/references`.

**Sort key:** `ORDER BY cited_citation_count DESC` — NOT `papers.citation_count`, which may differ due to earlier INSERT OR IGNORE from a different API call.

Query methodology ancestors: `SELECT cited_paper_id FROM references WHERE paper_id = X AND intents LIKE '%methodology%'`

---

### `citations`
Papers that cite paper X (descendants / newer work). Each row is always read and
written with `paper_id = X` — the paper being cited.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT FK → papers | The paper being cited |
| `citing_paper_id` | TEXT FK → papers | The paper that cites it |
| `is_influential` | INT | 1 if S2 marked it influential |
| `intents` | TEXT | JSON array e.g. `["methodology", "background"]` |
| `citing_citation_count` | INT | `citationCount` from this `/citations` API batch. **Used for ORDER BY on cache read** so warm-run sort order matches cold-run in-memory sort. |
| `year_window_start` | INT | Start year used when this batch was fetched |
| `year_window_end` | INT | End year used when this batch was fetched |
| `fetched_at` | TEXT | ISO timestamp |

Primary key: `(paper_id, citing_paper_id)`

**Cache hit:** any row exists where `paper_id = X` for the requested year window → skip `GET /paper/X/citations`.

**Sort key:** `ORDER BY citing_citation_count DESC` — NOT `papers.citation_count`.

Query methodology descendants: `SELECT citing_paper_id FROM citations WHERE paper_id = X AND intents LIKE '%methodology%' AND citing_paper_id IN (SELECT paper_id FROM papers WHERE year BETWEEN ? AND ?)`

---

### `lineage`
The single Gemini-selected predecessor per paper. Written by `pipeline.py` only.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT PK FK → papers | The target (newer) paper |
| `predecessor_id` | TEXT FK → papers | NULL if foundational |
| `is_foundational` | INT | 1 if no predecessor |
| `selection_reasoning` | TEXT | Gemini's explanation of why this predecessor was chosen |

**Cache hit:** row exists → skip Step 3 (references fetch) and Step 4 (Gemini selection).

Query successors: `SELECT paper_id FROM lineage WHERE predecessor_id = X`
Query predecessor: `SELECT predecessor_id FROM lineage WHERE paper_id = X`

---

### `analysis`
Gemini `target_analysis` block for each paper. Written by `pipeline.py` only.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT PK FK → papers | |
| `problem_addressed` | TEXT | |
| `core_method` | TEXT | |
| `key_innovation` | TEXT | |
| `limitations` | TEXT | JSON array of strings |
| `breakthrough_level` | TEXT | `minor` / `moderate` / `major` / `revolutionary` |
| `explanation_eli5` | TEXT | |
| `explanation_intuitive` | TEXT | |
| `explanation_technical` | TEXT | |
| `analyzed_at` | TEXT | ISO timestamp |

**Cache hit:** row exists → skip Gemini `analyze_step()` call.

---

### `comparison`
How a paper improved upon its predecessor (`comparison` block from Gemini).
No row for foundational papers.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT PK FK → papers | The newer paper |
| `predecessor_id` | TEXT FK → papers | |
| `what_was_improved` | TEXT | |
| `how_it_was_improved` | TEXT | |
| `why_it_matters` | TEXT | |
| `problem_solved_from_predecessor` | TEXT | |
| `remaining_limitations` | TEXT | JSON array of strings |

Missing row = foundational paper (no comparison exists).

---

### `secondary_influences`
Other papers that influenced the target beyond the primary predecessor.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT FK → papers | The target paper |
| `influenced_by_id` | TEXT | S2 paper ID (may not be in `papers` table) |
| `contribution` | TEXT | |

Primary key: `(paper_id, influenced_by_id)`

---

### `feedback`
User feedback on pipeline outputs. One row per feedback submission.
Covers both tree view (edge correctness) and LLM explanation view (selection + analysis quality).

| Column | Type | Notes |
|--------|------|-------|
| `feedback_id` | TEXT PK | UUID |
| `paper_id` | TEXT FK → papers | The main paper being rated |
| `related_paper_id` | TEXT FK → papers | The other paper in the relationship (NULL for analysis feedback) |
| `view_type` | TEXT | `tree` or `llm` |
| `feedback_target` | TEXT | See values below |
| `rating` | INT | `1` = correct / helpful, `-1` = wrong / unhelpful |
| `comment` | TEXT | Optional free-text from user |
| `created_at` | TEXT | ISO timestamp |

`feedback_target` values:

| Value | View | What is being rated | `paper_id` | `related_paper_id` |
|-------|------|---------------------|------------|-------------------|
| `predecessor` | llm | Was Gemini's predecessor pick correct? | target paper | selected predecessor |
| `analysis` | llm | Was the explanation accurate? | target paper | NULL |
| `comparison` | llm | Was the improvement description accurate? | target paper | predecessor |
| `tree_ancestor` | tree | Is this ancestor connection valid? | source paper | cited paper |
| `tree_descendant` | tree | Is this descendant connection valid? | cited paper | citing paper |

---

### `trees`
One row per `build_tree()` run from `tree_builder.py`.

| Column | Type | Notes |
|--------|------|-------|
| `tree_id` | TEXT PK | `{root_paper_id}_{YYYYMMDD_HHMMSS}` |
| `root_paper_id` | TEXT FK → papers | |
| `generated_at` | TEXT | ISO timestamp |
| `max_depth` | INT | |
| `max_children` | INT | |
| `window_years` | INT | Years searched for descendants |

### `tree_nodes`
Every paper node in a tree run, with its position and relationship to its parent.

| Column | Type | Notes |
|--------|------|-------|
| `tree_id` | TEXT FK → trees | |
| `paper_id` | TEXT FK → papers | |
| `node_type` | TEXT | `target` / `ancestor` / `descendant` |
| `depth` | INT | 0 = root |
| `parent_paper_id` | TEXT | FK → papers, NULL for root |

Primary key: `(tree_id, paper_id)`

Reconstruct a tree: `SELECT * FROM tree_nodes JOIN papers USING(paper_id) WHERE tree_id = ? ORDER BY node_type, depth`

---

### `fetch_log`
One row per `(paper, fetch_type, year_window)` combination — records every API call to
`/references` or `/citations`, including calls that returned null or empty results.

| Column | Type | Notes |
|--------|------|-------|
| `paper_id` | TEXT FK → papers | The paper whose edges were fetched |
| `fetch_type` | TEXT | `references` or `citations` |
| `year_start` | INT | `0` for references (no window); start year for citations |
| `year_end` | INT | `0` for references (no window); end year for citations |
| `result_count` | INT | Number of rows returned by the API. **`0` = API returned null or empty** |
| `fetched_at` | TEXT | ISO timestamp |

Primary key: `(paper_id, fetch_type, year_start, year_end)`

**Purpose.** `has_references()` and `has_citations()` check this table rather than
counting rows in `references`/`citations`. This means a paper that returned no results
is still marked as fetched — preventing the same API call from being retried on every
visit and on every subsequent run.

**Cache hit:** `SELECT COUNT(*) FROM fetch_log WHERE paper_id = ? AND fetch_type = 'references'`  
**Zero-result hit:** row exists with `result_count = 0` → no data to read, skip API call  
**UI use:** `result_count = 0` lets the UI display "no references found in S2" instead of a missing node

---

## Relationships

```
papers ──────────────────────────────────────────────────────┐
  │                                                           │
  ├── references       (paper_id → cited_paper_id)            │ raw S2 — ancestors
  ├── citations        (paper_id ← citing_paper_id)           │ raw S2 — descendants
  ├── fetch_log        (1:N — one row per fetch attempt)       │ fetch audit log
  │                                                           │
  ├── lineage          (paper_id → predecessor_id)            │ Gemini pick
  ├── analysis         (1:1)                                  │ Gemini analysis
  ├── comparison       (1:1, nullable)                        │ Gemini comparison
  ├── secondary_influences (1:N)                              │
  │                                                           │
  ├── tree_nodes       (N:N via trees)                        │ tree runs
  └── feedback         (1:N, both views)                      │ user ratings
```

---

## Design Decisions

### `fetch_log` — tracking empty and null API responses

**Problem.**
`has_references(paper_id)` previously checked `SELECT COUNT(*) FROM references WHERE paper_id = ?`.
If the `/references` API returned `null` or an empty list (paper has no S2-indexed references),
`save_references` inserted nothing, and `has_references` stayed False. Every subsequent visit
to that paper — including revisits via different parent paths within the same tree build, and
every future warm run — triggered a fresh API call that returned the same null response.
The same bug applied to `has_citations` / `save_citations` for citation windows.

**Fix.**
A dedicated `fetch_log` table records every API call outcome, regardless of result count:

```sql
INSERT OR REPLACE INTO fetch_log
    (paper_id, fetch_type, year_start, year_end, result_count, fetched_at)
VALUES (?, 'references', 0, 0, <count>, ?)
```

`save_references` and `save_citations` always write to `fetch_log` as their last step,
even when `refs_data` / `cites_data` is empty. `tree_builder.py` also calls
`save_references(paper_id, [])` on all early-exit paths (null data, no data key) before
returning, ensuring no API call goes unrecorded.

`has_references` and `has_citations` now check `fetch_log` only:

```sql
-- references
SELECT COUNT(*) FROM fetch_log
WHERE paper_id = ? AND fetch_type = 'references'

-- citations (year-windowed)
SELECT COUNT(*) FROM fetch_log
WHERE paper_id = ? AND fetch_type = 'citations'
  AND year_start = ? AND year_end = ?
```

**`result_count = 0` meaning.**
A row with `result_count = 0` means the API call was made and returned no usable data.
The `references` / `citations` tables will have no corresponding rows for this paper.
This is intentionally exposed via `get_paper()` (`referencesFetched`, `referencesResultCount`)
so the UI can distinguish "never fetched" from "fetched, S2 has no data".

---

### Edge-level citation counts (`cited_citation_count`, `citing_citation_count`)

**Problem.**
`papers.citation_count` is written by `INSERT OR IGNORE` — whichever API batch
first encounters a paper wins, and all later encounters are silently ignored.
The same paper can appear as metadata in many different batch responses during a
single cold run (e.g. BERT appears in Attention's 9,000-row citations batch AND
in ResNet's references batch, minutes apart, with slightly different counts
because S2 citation counts are live and approximate).

The cold run sorts candidates **in-memory from the live API batch**, using whatever
count that specific response returned.  
The warm run sorts via SQL using `papers.citation_count`, which may be from an
entirely different earlier batch — causing a different rank and therefore a
different top-N selection. At depth 2–3 this is enough to produce completely
different papers.

**Why not just `INSERT OR REPLACE`?**
Even if `papers` always stored the latest count, the warm run would sort by the
count from the *last* batch to run, not the batch that originally ranked the edge.
The mismatch would still exist, just in a different direction.

**Fix.**
Store the citation count directly on the edge row at insert time:

- `references.cited_citation_count` — count from the `/references` batch that
  created this edge
- `citations.citing_citation_count` — count from the `/citations` batch that
  created this edge

Cache reads sort by the **edge-level count**, not `papers.citation_count`:

```sql
-- ancestors
ORDER BY r.cited_citation_count DESC

-- descendants
ORDER BY c.citing_citation_count DESC
```

This guarantees the warm run produces an identical top-N selection to the cold run
because both use the count from the same API call. `papers.citation_count` is
retained for display purposes only (shown in visualizer tooltips) and is not used
for any ranking logic.

---

## Cache Lookup Logic

### `tree_builder.py` — `build_tree("ARXIV:1706.03762")`

The caller always passes an arXiv ID (`ARXIV:<number>`).

```
0. Resolve paper identity
   cache.get_paper("ARXIV:1706.03762")
     → SELECT WHERE paper_id = 'ARXIV:1706.03762'   -- miss (no such PK row)
     → SELECT WHERE arxiv_id = '1706.03762'          -- HIT if fetched before
   If miss on both → call GET /paper/ARXIV:1706.03762
     → API returns { paperId: "204e3073...", ... }
     → INSERT INTO papers (paper_id='204e3073...', arxiv_id='1706.03762', ...)
     → future lookups by arxiv_id now hit the cache

1. paper in papers? (checked via step 0 above)
   YES → use cached title, year, citation_count — skip GET /paper/{id}
   NO  → call API, INSERT into papers (with arxiv_id populated)

2. fetch_log row for (paper_id, 'references')?
   YES → query references for methodology ancestors (may return empty if result_count=0)
         skip GET /paper/{s2_id}/references
   NO  → call API, INSERT rows into references + papers,
         INSERT into fetch_log (result_count = number saved, or 0 if null/empty)

3. fetch_log row for (paper_id, 'citations', year_start, year_end)?
   YES → query citations for methodology descendants in year window (may return empty if result_count=0)
         skip GET /paper/{s2_id}/citations
   NO  → call paginated API, INSERT rows into citations + papers,
         INSERT into fetch_log (result_count = number saved, or 0 if null/empty)

4. Store run → INSERT into trees + tree_nodes
```

### `pipeline.py` — `build_timeline("ARXIV:1706.03762")`

Same arXiv ID entry point; same two-step paper resolution as above.

```
0. Resolve paper identity — same as tree_builder step 0

1. paper in papers AND pdf_s3_uri IS NOT NULL?
   YES → read PDF from S3 directly, skip S2 fetch + arXiv download + S3 upload
   NO  → call S2 to get arXiv ID (already in arxiv_id col after step 0),
         download PDF, upload to S3, UPDATE papers SET pdf_s3_uri, source_type

2. paper in lineage?
   YES → use cached predecessor_id + selection_reasoning, skip references fetch + Gemini selection
   NO  → call S2 references, run Gemini, INSERT into lineage (with selection_reasoning)

3. paper in analysis?
   YES → skip Gemini analyze_step()
   NO  → run Gemini, INSERT into analysis + comparison + secondary_influences
```

---

## Cross-Tree Cache Reuse

The cache is **paper-centric, not tree-centric**. Every paper node visited in any tree
build writes its data to the shared `papers`, `references`, `citations`, and `fetch_log`
tables. When a subsequent `build_tree()` call reaches the same paper — regardless of
which paper is the new root — it finds the data already present and skips the API call.

### What gets reused

| Data | Reused when |
|------|-------------|
| Paper metadata (`papers` row) | Any tree that encounters the same `paper_id` anywhere in its traversal |
| References (`references` rows + `fetch_log`) | Any tree that traverses into this paper as an **ancestor** |
| Citations for a year window (`citations` rows + `fetch_log`) | Any tree that traverses into this paper as a **descendant root** for the same window |

### Role affects what is fetched

A paper's role in a given tree determines which API calls are made for it:

- **Ancestor node** — only `/references` is fetched (what it cites). Its own
  `/citations` are not fetched because it is not a descendant root in this tree.
- **Descendant root** — only `/citations` is fetched for the relevant year window
  (what cites it). Its own `/references` are not fetched because it is not an
  ancestor root in this tree.
- **Root paper** — both `/references` (ancestors branch) and `/citations`
  (descendants branch) are fetched.

This means building a tree rooted at a **predecessor** (e.g. ResNet) reuses all the
ancestor metadata already in the DB but still fetches ResNet's own citations fresh —
because when ResNet appeared as an ancestor of the Transformer tree, its citations
were never needed.

Conversely, building a tree rooted at a **successor** (e.g. Diffusion Models) gets
full cache hits on its descendant data (fetched during the Transformer tree's
descendant pass) but fetches its ancestor data fresh — except for any nodes that were
already fetched as ancestors in a previous tree.

### Observed example (seed = Transformer `204e3073`)

```
Build seed tree (Transformer):
  → ResNet, Adam, Bahdanau fetched as ancestors   → references saved to fetch_log
  → Diffusion, BERT, GPT fetched as descendants   → citations (windowed) saved to fetch_log

Build predecessor tree (ResNet `2c03df8b`):
  → ResNet metadata:          CACHE HIT  (papers row from seed tree)
  → ResNet references depth=0: CACHE HIT  (fetch_log row from seed tree)
  → AlexNet, VGG refs:        CACHE HIT  (fetched as depth-2 ancestors in seed tree)
  → ResNet citations window:  API CALL   (ResNet was never a descendant root — not fetched)
  → New depth-2 papers via VGG: API CALL (not reachable from Transformer's traversal path)

Build successor tree (Diffusion `5c126ae3`):
  → Diffusion metadata:          CACHE HIT  (papers row from seed tree)
  → Diffusion citations depth=0: CACHE HIT  (fetch_log row — was seed's descendant)
  → depth-1 descendants:         CACHE HIT  (also in seed tree descendant pass)
  → Diffusion references:        API CALL   (Diffusion was never an ancestor root)
  → Transformer references:      API CALL   (Transformer's own /references not fetched
                                             in seed tree — it was the root, its refs
                                             went to ancestors not stored under its own
                                             fetch_log entry at depth=1 of successor)
    → BUT Transformer's depth-2 ancestors (ResNet, Adam, Bahdanau):
                                 CACHE HIT  (already in fetch_log from seed tree)
```

---

## File Location

```
ResearchLineage/
├── DATABASE_SCHEMA.md        ← this file
├── lineage_cache.db          ← SQLite file (gitignored)
├── timeline_view/
│   ├── pipeline.py
│   └── cache.py              ← module implementing reads/writes
└── tree_view/
    ├── tree_builder.py
    └── cache.py              ← same module or shared
```

`lineage_cache.db` is a runtime artifact — add to `.gitignore`.
