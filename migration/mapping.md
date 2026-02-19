# Phase 3 — Field Mapping: Semantic Scholar API → PostgreSQL Schema

FK insert order: `authors` → `papers` → `paper_authors` → `citations` → `paper_external_ids` → `citation_paths` → `citation_path_nodes`

---

## papers

| API Field | API Path | DB Column | Type | Transform | Notes |
|-----------|----------|-----------|------|-----------|-------|
| `paperId` | `paper.paperId` | `paper_id` | TEXT | identity | Semantic Scholar 40-char hex |
| `title` | `paper.title` | `title` | TEXT | identity | Required; never null from API |
| `abstract` | `paper.abstract` | `abstract` | TEXT | identity | May be null; store as NULL |
| `venue` | `paper.venue` | `venue` | TEXT | identity | Short venue name |
| `year` | `paper.year` | `year` | INTEGER | identity | May be null for pre-prints |
| `publicationDate` | `paper.publicationDate` | `publication_date` | DATE | `YYYY-MM-DD` parse | May be null |
| `citationCount` | `paper.citationCount` | `citation_count` | INTEGER | `or 0` | Default 0 if null |
| `influentialCitationCount` | `paper.influentialCitationCount` | `influential_citation_count` | INTEGER | `or 0` | Default 0 if null |
| `isOpenAccess` | `paper.isOpenAccess` | `is_open_access` | BOOLEAN | `or False` | Default False |
| `url` | `paper.url` | `source_url` | TEXT | identity | Semantic Scholar page URL |
| *(not in API)* | — | `s3_pdf_key` | TEXT | NULL | Set after PDF download |

**Data issues:**
- `year` can be `None` for very recent pre-prints → use `NULL`, not 0.
- `abstract` can be `None` → store as `NULL`.
- `venue` may be empty string `""` → normalise to `NULL`.

---

## authors

| API Field | API Path | DB Column | Transform | Notes |
|-----------|----------|-----------|-----------|-------|
| `authorId` | `paper.authors[].authorId` | `author_id` | identity | May be null for unknown authors — skip row |
| `name` | `paper.authors[].name` | `name` | strip whitespace | |

**Data issues:**
- Authors without `authorId` (rare): skip entirely — no stable key to use.
- Duplicate authors appear across papers — use `ON CONFLICT DO NOTHING`.

---

## paper_authors

| Source | DB Column | Transform |
|--------|-----------|-----------|
| `paper.paperId` | `paper_id` | identity |
| `paper.authors[].authorId` | `author_id` | skip if null |
| index in authors array (0-based) | `author_order` | `index + 1` (1-based) |

---

## citations

| Source | DB Column | Transform | Notes |
|--------|-----------|-----------|-------|
| seed paper_id | `citing_paper_id` | identity | When processing `/references` |
| `citedPaper.paperId` | `cited_paper_id` | identity | |
| seed paper_id | `cited_paper_id` | identity | When processing `/citations` |
| `citingPaper.paperId` | `citing_paper_id` | identity | |
| `intents` | `citation_context` | `', '.join(intents)` | e.g. `"methodology, background"` |

**Data issues:**
- `intents` may be empty list → store `NULL`.
- Self-citation guard in DB (`CHECK citing != cited`) — filter before insert.

---

## paper_external_ids

| API Field | DB `source` | DB `external_id` | Notes |
|-----------|-------------|------------------|-------|
| `externalIds.ArXiv` | `'arxiv'` | e.g. `"1706.03762"` | |
| `externalIds.DBLP` | `'dblp'` | e.g. `"conf/nips/..."` | |
| `externalIds.CorpusId` | `'corpus'` | str(int) | Convert integer to string |
| `externalIds.DOI` | `'doi'` | e.g. `"10.48550/arXiv.1706.03762"` | |
| `externalIds.PubMed` | `'pubmed'` | string | |
| `externalIds.MAG` | `'mag'` | str(int) | |

**Data issues:**
- All `externalIds` keys are optional; only insert rows where value is not `None`.
- `CorpusId` is an integer in the API response → cast to `TEXT`.

---

## paper_embeddings

Not populated by Semantic Scholar API. Must be generated separately.

**Recommended approach:**
```python
import openai
response = openai.embeddings.create(
    model="text-embedding-ada-002",
    input=paper["abstract"] or paper["title"]
)
vector = response.data[0].embedding  # list of 1536 floats
```

Insert with:
```sql
INSERT INTO paper_embeddings (paper_id, model_name, embedding, embedding_dimension)
VALUES (%s, 'text-embedding-ada-002', %s::vector, 1536)
ON CONFLICT (paper_id, model_name) DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = NOW();
```

---

## paper_sections

Not populated by Semantic Scholar API. Requires PDF download + parsing.

**Recommended approach:**
1. Download PDF from `openAccessPdf.url` (if `is_open_access = true`)
2. Parse with `PyMuPDF` or `pdfplumber`
3. Split into sections by heading detection
4. Embed each section with the same embedding model

---

## citation_paths / citation_path_nodes

Derived from the tree traversal in `tree_builder.py`. Not directly from a single API response.

| Source | DB Column | Notes |
|--------|-----------|-------|
| `gen_random_uuid()` | `path_id` | Generated at insert time |
| seed `paper_id` | `seed_paper_id` | The paper that triggered the tree build |
| `max_depth` param | `max_depth` | From `TreeView.build_tree()` args |
| computed | `path_score` | Optional; NULL if not scored |
| node `paper_id` | `paper_id` | Each paper in the traversal |
| traversal depth | `depth` | 0 = seed, 1 = direct ref/citation, etc. |
| traversal order | `position` | 1-based sequential position in path |
| `isInfluential` | `is_influential` | From citation edge metadata |
| `intents` joined | `influence_reason` | e.g. `"methodology"` |

---

## Transformation Summary

```
Semantic Scholar API
        │
        ▼
01_fetch_and_analyze.py   →  raw_papers.json
                             raw_citations.json
                             raw_references.json
        │
        ▼
02_transform_to_sql.py    →  insert_authors.sql
                             insert_papers.sql
                             insert_paper_authors.sql
                             insert_citations.sql
                             insert_external_ids.sql
                             insert_citation_paths.sql   (from tree cache)
                             insert_all.sql              (combined)
        │
        ▼
psql "$DB_URL" -f insert_all.sql
```
