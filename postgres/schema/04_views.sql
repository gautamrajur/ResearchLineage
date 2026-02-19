-- =============================================================================
-- ResearchLineage — 04_views.sql
-- Convenience views for common query patterns
-- Run AFTER 01_tables.sql, 02_indexes.sql, 03_audit_columns.sql
-- =============================================================================


-- =============================================================================
-- v_papers_with_authors
-- Every paper alongside its ordered author list as an array and as a string.
-- =============================================================================
CREATE OR REPLACE VIEW v_papers_with_authors AS
SELECT
    p.paper_id,
    p.title,
    p.abstract,
    p.venue,
    p.year,
    p.publication_date,
    p.citation_count,
    p.influential_citation_count,
    p.is_open_access,
    p.source_url,
    -- Ordered array of author names
    ARRAY_AGG(a.name ORDER BY pa.author_order) FILTER (WHERE a.name IS NOT NULL) AS authors,
    -- Comma-separated string for display
    STRING_AGG(a.name, ', ' ORDER BY pa.author_order) FILTER (WHERE a.name IS NOT NULL) AS authors_display,
    -- Count of authors
    COUNT(pa.author_id) AS author_count
FROM papers p
LEFT JOIN paper_authors pa ON pa.paper_id = p.paper_id
LEFT JOIN authors       a  ON a.author_id  = pa.author_id
GROUP BY
    p.paper_id, p.title, p.abstract, p.venue, p.year,
    p.publication_date, p.citation_count, p.influential_citation_count,
    p.is_open_access, p.source_url;

COMMENT ON VIEW v_papers_with_authors IS
    'Papers with their ordered author list. authors[] is ordered; authors_display is comma-separated.';


-- =============================================================================
-- v_citation_summary
-- For each paper: how many papers it cites (out-degree) and how many cite it
-- (in-degree), plus the full citation counts from the papers table.
-- =============================================================================
CREATE OR REPLACE VIEW v_citation_summary AS
SELECT
    p.paper_id,
    p.title,
    p.year,
    p.venue,
    p.citation_count                                            AS stored_citation_count,
    p.influential_citation_count,
    -- Graph-computed degrees from the citations table
    COUNT(DISTINCT out_c.cited_paper_id)                        AS references_count,   -- papers this paper cites
    COUNT(DISTINCT in_c.citing_paper_id)                        AS cited_by_count       -- papers that cite this paper
FROM papers p
LEFT JOIN citations out_c ON out_c.citing_paper_id = p.paper_id
LEFT JOIN citations in_c  ON in_c.cited_paper_id   = p.paper_id
GROUP BY
    p.paper_id, p.title, p.year, p.venue,
    p.citation_count, p.influential_citation_count
ORDER BY p.citation_count DESC;

COMMENT ON VIEW v_citation_summary IS
    'Citation in/out degree per paper from the local citations table, plus stored Semantic Scholar counts.';


-- =============================================================================
-- v_influential_papers
-- Papers ranked by influential_citation_count, enriched with author list.
-- Useful as a leaderboard / discovery view.
-- =============================================================================
CREATE OR REPLACE VIEW v_influential_papers AS
SELECT
    p.paper_id,
    p.title,
    p.year,
    p.venue,
    p.citation_count,
    p.influential_citation_count,
    p.is_open_access,
    p.source_url,
    -- Ratio: what fraction of citations are influential
    CASE
        WHEN p.citation_count > 0
        THEN ROUND((p.influential_citation_count::NUMERIC / p.citation_count) * 100, 2)
        ELSE 0
    END AS influence_ratio_pct,
    STRING_AGG(a.name, ', ' ORDER BY pa.author_order) FILTER (WHERE a.name IS NOT NULL) AS authors_display,
    -- External arXiv ID if available
    (SELECT external_id FROM paper_external_ids e WHERE e.paper_id = p.paper_id AND e.source = 'arxiv' LIMIT 1) AS arxiv_id
FROM papers p
LEFT JOIN paper_authors pa ON pa.paper_id = p.paper_id
LEFT JOIN authors       a  ON a.author_id  = pa.author_id
GROUP BY
    p.paper_id, p.title, p.year, p.venue,
    p.citation_count, p.influential_citation_count,
    p.is_open_access, p.source_url
ORDER BY p.influential_citation_count DESC, p.citation_count DESC;

COMMENT ON VIEW v_influential_papers IS
    'Papers ranked by influential citation count, with influence ratio and author info.';
