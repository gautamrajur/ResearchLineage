-- =============================================================================
-- insert_external_ids.sql
-- Source: Schema_MLOps.pdf paper_external_ids table
-- Run AFTER insert_papers.sql
-- A paper can have multiple external IDs (one per source)
-- =============================================================================

INSERT INTO paper_external_ids (paper_id, source, external_id)
VALUES
  ('P1', 'arxiv',  '1706.03762'),
  ('P1', 'corpus', '214736881'),
  ('P2', 'arxiv',  '1810.04805'),
  ('P3', 'arxiv',  '1806.00136'),
  ('P4', 'arxiv',  '2005.14165'),
  ('P7', 'arxiv',  '1512.03385'),
  ('P8', 'arxiv',  '2010.11929')
ON CONFLICT (paper_id, source) DO UPDATE SET
  external_id = EXCLUDED.external_id,
  updated_at  = NOW();
