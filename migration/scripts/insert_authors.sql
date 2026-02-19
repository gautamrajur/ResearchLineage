-- =============================================================================
-- insert_authors.sql
-- Source: Schema_MLOps.pdf sample data (A1–A8)
-- Run BEFORE insert_papers.sql (no dependencies)
-- =============================================================================

INSERT INTO authors (author_id, name)
VALUES
  ('A1', 'Ashish Vaswani'),
  ('A2', 'Jacob Devlin'),
  ('A3', 'Alec Radford'),
  ('A4', 'Kaiming He'),
  ('A5', 'Tom Brown'),
  ('A6', 'Edward J. Hu'),
  ('A7', 'Jason Wei'),
  ('A8', 'Long Ouyang')
ON CONFLICT (author_id) DO UPDATE SET
  name       = EXCLUDED.name,
  updated_at = NOW();
