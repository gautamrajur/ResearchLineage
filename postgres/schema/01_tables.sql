-- =============================================================================
-- ResearchLineage — 01_tables.sql
-- Academic Paper Citation Database — Table Definitions
-- PostgreSQL 15  |  Requires: pgvector extension
-- =============================================================================

-- Enable pgvector (must run before any vector column is created)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable gen_random_uuid() (built-in since PG13, no extension needed)
-- uuid_generate_v4() requires "uuid-ossp"; gen_random_uuid() does not.


-- =============================================================================
-- 1. authors
--    Central registry of all paper authors. Normalised to prevent redundancy.
-- =============================================================================
CREATE TABLE IF NOT EXISTS authors (
    author_id   TEXT        NOT NULL,
    name        TEXT        NOT NULL,

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT authors_pkey PRIMARY KEY (author_id)
);

COMMENT ON TABLE  authors             IS 'Unique authors across all papers.';
COMMENT ON COLUMN authors.author_id  IS 'Semantic Scholar author ID or internal surrogate key.';
COMMENT ON COLUMN authors.name       IS 'Full display name of the author.';


-- =============================================================================
-- 2. papers
--    Central entity. Every other table references paper_id.
-- =============================================================================
CREATE TABLE IF NOT EXISTS papers (
    paper_id                    TEXT        NOT NULL,
    title                       TEXT        NOT NULL,
    abstract                    TEXT,
    venue                       TEXT,
    year                        INTEGER     CHECK (year >= 1900 AND year <= date_part('year', CURRENT_DATE)::INTEGER + 1),
    publication_date            DATE,
    citation_count              INTEGER     NOT NULL DEFAULT 0 CHECK (citation_count >= 0),
    influential_citation_count  INTEGER     NOT NULL DEFAULT 0 CHECK (influential_citation_count >= 0),
    is_open_access              BOOLEAN     NOT NULL DEFAULT FALSE,
    s3_pdf_key                  TEXT,       -- S3 object key for stored PDF, nullable
    source_url                  TEXT,       -- Canonical URL (e.g. Semantic Scholar page)

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT papers_pkey PRIMARY KEY (paper_id)
);

COMMENT ON TABLE  papers                              IS 'Primary metadata for each academic paper.';
COMMENT ON COLUMN papers.paper_id                    IS 'Semantic Scholar paperId (40-char hex) or internal key.';
COMMENT ON COLUMN papers.year                        IS 'Publication year. Must be 1900–current+1 to allow pre-prints.';
COMMENT ON COLUMN papers.influential_citation_count  IS 'Count of citations flagged as influential by Semantic Scholar.';
COMMENT ON COLUMN papers.s3_pdf_key                  IS 'S3 object key; NULL when PDF is not stored.';


-- =============================================================================
-- 3. paper_authors
--    Many-to-many join between papers and authors, with ordering.
-- =============================================================================
CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id        TEXT    NOT NULL,
    author_id       TEXT    NOT NULL,
    author_order    INTEGER NOT NULL CHECK (author_order >= 1),

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT paper_authors_pkey         PRIMARY KEY (paper_id, author_id),
    CONSTRAINT paper_authors_fk_paper     FOREIGN KEY (paper_id)  REFERENCES papers  (paper_id) ON DELETE CASCADE,
    CONSTRAINT paper_authors_fk_author    FOREIGN KEY (author_id) REFERENCES authors (author_id) ON DELETE CASCADE
);

COMMENT ON TABLE  paper_authors              IS 'Maps papers to authors with positional ordering.';
COMMENT ON COLUMN paper_authors.author_order IS 'Position of the author on the paper (1 = first author).';


-- =============================================================================
-- 4. citations
--    Core citation graph. Records directed edges: citing → cited.
--    Self-citations are prohibited.
-- =============================================================================
CREATE TABLE IF NOT EXISTS citations (
    citing_paper_id  TEXT NOT NULL,
    cited_paper_id   TEXT NOT NULL,
    citation_context TEXT,    -- Optional: verbatim text surrounding the citation

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT citations_pkey              PRIMARY KEY (citing_paper_id, cited_paper_id),
    CONSTRAINT citations_no_self_ref       CHECK (citing_paper_id <> cited_paper_id),
    CONSTRAINT citations_fk_citing_paper   FOREIGN KEY (citing_paper_id) REFERENCES papers (paper_id) ON DELETE CASCADE,
    CONSTRAINT citations_fk_cited_paper    FOREIGN KEY (cited_paper_id)  REFERENCES papers (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  citations                   IS 'Directed citation edges between papers.';
COMMENT ON COLUMN citations.citation_context  IS 'Text snippet from the citing paper where the citation appears.';


-- =============================================================================
-- 5. paper_external_ids
--    Maps internal paper_id to IDs in external databases (arXiv, DBLP, etc.).
--    A single paper may have multiple external IDs (one per source).
-- =============================================================================
CREATE TABLE IF NOT EXISTS paper_external_ids (
    paper_id    TEXT NOT NULL,
    source      TEXT NOT NULL,   -- e.g. 'arxiv', 'dblp', 'corpus', 'pubmed'
    external_id TEXT NOT NULL,

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT paper_external_ids_pkey      PRIMARY KEY (paper_id, source),
    CONSTRAINT paper_external_ids_fk_paper  FOREIGN KEY (paper_id) REFERENCES papers (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  paper_external_ids             IS 'External identifiers for each paper across academic databases.';
COMMENT ON COLUMN paper_external_ids.source      IS 'External database name (arxiv, dblp, corpus, pubmed, …).';
COMMENT ON COLUMN paper_external_ids.external_id IS 'The paper''s ID in the external system (e.g. "1706.03762" for arXiv).';


-- =============================================================================
-- 6. paper_embeddings
--    One row per paper per model. Stores the full-paper vector embedding.
--    Default dimension: 1536 (OpenAI text-embedding-ada-002).
--    Use embedding_dimension to know the actual size when querying.
-- =============================================================================
CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_id             TEXT        NOT NULL,
    model_name           TEXT        NOT NULL,   -- e.g. 'text-embedding-ada-002'
    embedding            vector(1536),            -- NULL until embedding is generated
    embedding_dimension  INTEGER     CHECK (embedding_dimension > 0),

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT paper_embeddings_pkey      PRIMARY KEY (paper_id, model_name),
    CONSTRAINT paper_embeddings_fk_paper  FOREIGN KEY (paper_id) REFERENCES papers (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  paper_embeddings                    IS 'Full-paper vector embeddings for semantic search.';
COMMENT ON COLUMN paper_embeddings.model_name         IS 'Embedding model used (determines vector space).';
COMMENT ON COLUMN paper_embeddings.embedding          IS 'pgvector column — 1536-dim for OpenAI Ada.';
COMMENT ON COLUMN paper_embeddings.embedding_dimension IS 'Actual dimension; useful when switching models.';


-- =============================================================================
-- 7. paper_sections
--    Breaks a paper into named sections (Introduction, Methodology, etc.).
--    Each section has its own embedding for granular semantic search.
-- =============================================================================
CREATE TABLE IF NOT EXISTS paper_sections (
    section_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
    paper_id       TEXT        NOT NULL,
    section_title  TEXT        NOT NULL,
    content        TEXT,
    embedding      vector(1536),
    model_name     TEXT,

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT paper_sections_pkey      PRIMARY KEY (section_id),
    CONSTRAINT paper_sections_fk_paper  FOREIGN KEY (paper_id) REFERENCES papers (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  paper_sections               IS 'Per-section content and embeddings for granular analysis.';
COMMENT ON COLUMN paper_sections.section_id    IS 'Auto-generated UUID surrogate key.';
COMMENT ON COLUMN paper_sections.section_title IS 'Section heading (e.g. "Introduction", "Methodology").';


-- =============================================================================
-- 8. citation_paths
--    A named traversal path through the citation graph starting from a seed paper.
--    Nodes are stored in citation_path_nodes.
-- =============================================================================
CREATE TABLE IF NOT EXISTS citation_paths (
    path_id        UUID    NOT NULL DEFAULT gen_random_uuid(),
    seed_paper_id  TEXT    NOT NULL,
    max_depth      INTEGER NOT NULL CHECK (max_depth > 0),
    path_score     REAL    CHECK (path_score >= 0 AND path_score <= 1),

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT citation_paths_pkey          PRIMARY KEY (path_id),
    CONSTRAINT citation_paths_fk_seed_paper FOREIGN KEY (seed_paper_id) REFERENCES papers (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  citation_paths              IS 'A discovered citation traversal path originating from a seed paper.';
COMMENT ON COLUMN citation_paths.path_score   IS 'Composite relevance score in [0,1]; NULL if not scored.';


-- =============================================================================
-- 9. citation_path_nodes
--    Individual papers within a citation path, ordered by depth and position.
-- =============================================================================
CREATE TABLE IF NOT EXISTS citation_path_nodes (
    path_id           UUID    NOT NULL,
    paper_id          TEXT    NOT NULL,
    depth             INTEGER NOT NULL CHECK (depth >= 0),
    position          INTEGER NOT NULL CHECK (position >= 1),
    is_influential    BOOLEAN NOT NULL DEFAULT FALSE,
    influence_reason  TEXT,

    -- Audit
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT citation_path_nodes_pkey       PRIMARY KEY (path_id, paper_id),
    CONSTRAINT citation_path_nodes_fk_path    FOREIGN KEY (path_id)  REFERENCES citation_paths (path_id) ON DELETE CASCADE,
    CONSTRAINT citation_path_nodes_fk_paper   FOREIGN KEY (paper_id) REFERENCES papers          (paper_id) ON DELETE CASCADE
);

COMMENT ON TABLE  citation_path_nodes                  IS 'Papers that make up a citation path, with depth and position metadata.';
COMMENT ON COLUMN citation_path_nodes.depth            IS 'Distance from the seed paper (0 = seed itself).';
COMMENT ON COLUMN citation_path_nodes.position         IS 'Ordinal position within the path (1-based).';
COMMENT ON COLUMN citation_path_nodes.is_influential   IS 'Whether Semantic Scholar marked this as an influential citation.';
COMMENT ON COLUMN citation_path_nodes.influence_reason IS 'Human-readable reason for influence flag.';
