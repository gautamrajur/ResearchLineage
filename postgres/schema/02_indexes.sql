-- =============================================================================
-- ResearchLineage — 02_indexes.sql
-- Performance indexes and pgvector ANN indexes
-- Run AFTER 01_tables.sql
-- =============================================================================


-- =============================================================================
-- papers
-- =============================================================================

-- Fast lookups when searching by title substring (case-insensitive)
CREATE INDEX IF NOT EXISTS idx_papers_title
    ON papers USING GIN (to_tsvector('english', title));

-- Filter/sort by year (common in timeline views)
CREATE INDEX IF NOT EXISTS idx_papers_year
    ON papers (year);

-- Sort by citation popularity
CREATE INDEX IF NOT EXISTS idx_papers_citation_count
    ON papers (citation_count DESC);

CREATE INDEX IF NOT EXISTS idx_papers_influential_citation_count
    ON papers (influential_citation_count DESC);

-- Filter open-access papers
CREATE INDEX IF NOT EXISTS idx_papers_open_access
    ON papers (is_open_access) WHERE is_open_access = TRUE;


-- =============================================================================
-- authors
-- =============================================================================

-- Lookup authors by name (full-text)
CREATE INDEX IF NOT EXISTS idx_authors_name_fts
    ON authors USING GIN (to_tsvector('english', name));


-- =============================================================================
-- paper_authors
-- =============================================================================

-- Forward: all authors for a paper (already covered by PK prefix paper_id)
-- Reverse: all papers by an author
CREATE INDEX IF NOT EXISTS idx_paper_authors_author_id
    ON paper_authors (author_id);

-- Sort authors within a paper
CREATE INDEX IF NOT EXISTS idx_paper_authors_order
    ON paper_authors (paper_id, author_order);


-- =============================================================================
-- citations
-- =============================================================================

-- All papers citing a given paper (in-edges)
CREATE INDEX IF NOT EXISTS idx_citations_cited_paper_id
    ON citations (cited_paper_id);

-- All papers a given paper cites (out-edges) — covered by PK prefix citing_paper_id


-- =============================================================================
-- paper_external_ids
-- =============================================================================

-- Lookup by (source, external_id) — e.g. find internal ID from arXiv ID
CREATE INDEX IF NOT EXISTS idx_paper_external_ids_source_ext
    ON paper_external_ids (source, external_id);


-- =============================================================================
-- paper_embeddings — pgvector ANN index (IVFFlat)
-- =============================================================================
-- IVFFlat: approximate nearest neighbour, good balance of speed vs. recall.
-- lists=100 is a reasonable default for up to ~1M rows; tune with:
--   lists = max(1, sqrt(num_rows))  approximately
-- Run ANALYZE on the table before heavy ANN queries for best performance.

CREATE INDEX IF NOT EXISTS idx_paper_embeddings_ivfflat
    ON paper_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


-- =============================================================================
-- paper_sections — pgvector ANN index (IVFFlat)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_paper_sections_embedding_ivfflat
    ON paper_sections USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Full-text search on section content
CREATE INDEX IF NOT EXISTS idx_paper_sections_content_fts
    ON paper_sections USING GIN (to_tsvector('english', COALESCE(content, '')));

-- Look up all sections for a paper
CREATE INDEX IF NOT EXISTS idx_paper_sections_paper_id
    ON paper_sections (paper_id);


-- =============================================================================
-- citation_paths
-- =============================================================================

-- All paths originating from a seed paper
CREATE INDEX IF NOT EXISTS idx_citation_paths_seed_paper_id
    ON citation_paths (seed_paper_id);

-- Rank paths by score
CREATE INDEX IF NOT EXISTS idx_citation_paths_score
    ON citation_paths (path_score DESC NULLS LAST);


-- =============================================================================
-- citation_path_nodes
-- =============================================================================

-- All paths a paper appears in
CREATE INDEX IF NOT EXISTS idx_citation_path_nodes_paper_id
    ON citation_path_nodes (paper_id);

-- Traverse a path in depth/position order
CREATE INDEX IF NOT EXISTS idx_citation_path_nodes_depth_position
    ON citation_path_nodes (path_id, depth, position);

-- Filter influential nodes
CREATE INDEX IF NOT EXISTS idx_citation_path_nodes_influential
    ON citation_path_nodes (path_id, is_influential) WHERE is_influential = TRUE;
