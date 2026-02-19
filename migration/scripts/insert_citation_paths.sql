-- =============================================================================
-- insert_citation_paths.sql
-- Source: Schema_MLOps.pdf citation_paths + citation_path_nodes tables
-- Run AFTER insert_papers.sql
-- Two paths defined in the PDF:
--   UUID_LLM_Evolution     — seed: P1, depth 3, score 0.95
--   UUID_Vision_Transformers — seed: P7, depth 2, score 0.88
-- =============================================================================

-- Use stable UUIDs so this script is idempotent
INSERT INTO citation_paths (path_id, seed_paper_id, max_depth, path_score)
VALUES
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P1', 3, 0.95),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P7', 2, 0.88)
ON CONFLICT (path_id) DO UPDATE SET
  max_depth  = EXCLUDED.max_depth,
  path_score = EXCLUDED.path_score,
  updated_at = NOW();

-- ── Path 1: LLM Evolution (P1 → P3 → P4 → P12) ──────────────────────────────
INSERT INTO citation_path_nodes
  (path_id, paper_id, depth, position, is_influential, influence_reason)
VALUES
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P1',  0, 1, TRUE,  'Foundational Transformer'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P3',  1, 2, TRUE,  'Early GPT model'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P4',  2, 3, TRUE,  'Scaled-up LLM'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P12', 3, 4, FALSE, 'Instruction following')
ON CONFLICT (path_id, paper_id) DO UPDATE SET
  depth            = EXCLUDED.depth,
  position         = EXCLUDED.position,
  is_influential   = EXCLUDED.is_influential,
  influence_reason = EXCLUDED.influence_reason,
  updated_at       = NOW();

-- ── Path 2: Vision Transformers (P7 → P1 → P8) ───────────────────────────────
INSERT INTO citation_path_nodes
  (path_id, paper_id, depth, position, is_influential, influence_reason)
VALUES
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P7', 0, 1, TRUE, 'Foundational CNN'),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P1', 1, 2, TRUE, 'Transformer architecture'),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P8', 2, 3, TRUE, 'Vision Transformer application')
ON CONFLICT (path_id, paper_id) DO UPDATE SET
  depth            = EXCLUDED.depth,
  position         = EXCLUDED.position,
  is_influential   = EXCLUDED.is_influential,
  influence_reason = EXCLUDED.influence_reason,
  updated_at       = NOW();
