# Phase 2 — PostgreSQL Schema

Defines and deploys the 9-table Academic Paper Citation Database on Cloud SQL PostgreSQL 15.

---

## Files

| File | Purpose |
|------|---------|
| `01_tables.sql` | All 9 tables with constraints, comments, pgvector extension |
| `02_indexes.sql` | B-tree, GIN (full-text), and IVFFlat (pgvector ANN) indexes |
| `03_audit_columns.sql` | `fn_set_updated_at` trigger + `fn_protect_created_at` guard |
| `04_views.sql` | `v_papers_with_authors`, `v_citation_summary`, `v_influential_papers` |
| `deploy_schema.sh` | Automated deploy script with connection test and verification |
| `rollback_schema.sql` | DROP all objects in reverse dependency order |

---

## Prerequisites

- PostgreSQL 15 (Cloud SQL or local)
- `psql` client installed
- `pgvector` extension installable (Cloud SQL PG15 supports it natively)

---

## Deployment

### 1. Set the connection URL
```bash
export DB_URL="postgresql://rl_user:<password>@<public_ip>:5432/researchlineage"
```
Get `<public_ip>` from `terraform output public_ip`.

### 2. Run the deploy script
```bash
cd postgres/schema
./deploy_schema.sh
```

The script will:
1. Test the connection
2. Run files 01–04 in a single transaction per file
3. Print a verification summary of tables, views, and triggers

### 3. Verify manually (optional)
```sql
-- List all tables and their sizes
SELECT table_name, pg_size_pretty(pg_total_relation_size(table_name::regclass))
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Confirm pgvector is installed
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check all 18 audit triggers exist (9 tables × 2 triggers each)
SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg_%';
```

---

## Schema Design Decisions

### Primary keys
- `papers`, `authors`: `TEXT` — keeps Semantic Scholar IDs as natural keys, avoids surrogate key joins.
- `citation_paths`, `paper_sections`: `UUID` — no natural key exists; `gen_random_uuid()` is built-in since PG13.
- Composite PKs on junction tables (`paper_authors`, `citations`, `paper_external_ids`, `citation_path_nodes`).

### Foreign keys
All foreign keys use `ON DELETE CASCADE`. Rationale: if a paper is removed (e.g. data correction), all dependent rows (citations, embeddings, sections, paths) are automatically cleaned up. Change to `ON DELETE RESTRICT` in `01_tables.sql` if you prefer safer hard deletes.

### Constraints
| Constraint | Location | Rule |
|-----------|----------|------|
| No self-citations | `citations` | `CHECK (citing_paper_id <> cited_paper_id)` |
| Author order ≥ 1 | `paper_authors` | `CHECK (author_order >= 1)` |
| Year range | `papers` | `CHECK (year >= 1900 AND year <= current_year + 1)` |
| Citation counts ≥ 0 | `papers` | `CHECK (citation_count >= 0)` |
| Path score 0–1 | `citation_paths` | `CHECK (path_score >= 0 AND path_score <= 1)` |
| Embedding dimension > 0 | `paper_embeddings` | `CHECK (embedding_dimension > 0)` |

### Audit columns
- `created_at`: set once at `INSERT` via `DEFAULT NOW()`. A trigger raises an exception if you try to change it.
- `updated_at`: auto-updated by `fn_set_updated_at()` on every `UPDATE` where data actually changed (skips no-op updates using `row(NEW.*) IS DISTINCT FROM row(OLD.*)`).

### pgvector indexes
- Using **IVFFlat** with `lists=100` — good for datasets up to ~500K rows.
- Distance metric: `vector_cosine_ops` (cosine similarity, standard for text embeddings).
- For larger datasets (>1M rows), switch to **HNSW**: `USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`.

---

## Table Dependency Order

```
authors ──────────────────────────────────┐
                                          ↓
papers ───→ paper_authors                 │
       ───→ citations (self-ref)          │
       ───→ paper_external_ids            │
       ───→ paper_embeddings              │
       ───→ paper_sections                │
       ───→ citation_paths ───→ citation_path_nodes
```

This order matters for INSERT scripts (Phase 3).

---

## Rollback

```bash
psql "$DB_URL" -f rollback_schema.sql
```

> This drops **all tables, views, functions, and procedures**. All data is lost. Use only in dev/test.

---

## Next Steps → Phase 3

After the schema is deployed:
1. Go to `../../migration/`
2. Follow `README.md` there to run the data migration scripts
