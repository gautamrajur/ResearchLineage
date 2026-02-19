-- =============================================================================
-- ResearchLineage — rollback_schema.sql
-- Drops all schema objects in reverse dependency order.
-- WARNING: This is destructive. All data will be lost.
-- =============================================================================

-- Views (no dependencies — safe to drop first)
DROP VIEW IF EXISTS v_influential_papers    CASCADE;
DROP VIEW IF EXISTS v_citation_summary      CASCADE;
DROP VIEW IF EXISTS v_papers_with_authors   CASCADE;

-- Tables (FK dependency order — children before parents)
DROP TABLE IF EXISTS citation_path_nodes    CASCADE;
DROP TABLE IF EXISTS citation_paths         CASCADE;
DROP TABLE IF EXISTS paper_sections         CASCADE;
DROP TABLE IF EXISTS paper_embeddings       CASCADE;
DROP TABLE IF EXISTS paper_external_ids     CASCADE;
DROP TABLE IF EXISTS citations              CASCADE;
DROP TABLE IF EXISTS paper_authors          CASCADE;
DROP TABLE IF EXISTS papers                 CASCADE;
DROP TABLE IF EXISTS authors                CASCADE;

-- Audit functions and procedures
DROP PROCEDURE IF EXISTS attach_audit_triggers(TEXT);
DROP FUNCTION  IF EXISTS fn_protect_created_at();
DROP FUNCTION  IF EXISTS fn_set_updated_at();

-- Extension (only if no other schemas use pgvector)
-- DROP EXTENSION IF EXISTS vector;   -- Uncomment with caution
