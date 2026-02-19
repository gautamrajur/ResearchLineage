-- =============================================================================
-- insert_paper_authors.sql
-- Source: Schema_MLOps.pdf sample data
-- Run AFTER insert_authors.sql AND insert_papers.sql
-- Edge case: A3 (Alec Radford) appears on P3, P4, P11 — valid many-to-many
-- =============================================================================

INSERT INTO paper_authors (paper_id, author_id, author_order)
VALUES
  ('P1',  'A1', 1),  -- Ashish Vaswani  → Attention Is All You Need
  ('P2',  'A2', 1),  -- Jacob Devlin    → BERT
  ('P3',  'A3', 1),  -- Alec Radford    → GPT
  ('P4',  'A3', 1),  -- Alec Radford    → GPT-3 (1st author)
  ('P4',  'A5', 2),  -- Tom Brown       → GPT-3 (2nd author)
  ('P7',  'A4', 1),  -- Kaiming He      → ResNet
  ('P9',  'A6', 1),  -- Edward J. Hu    → LoRA
  ('P10', 'A7', 1),  -- Jason Wei       → Chain-of-Thought
  ('P11', 'A3', 1),  -- Alec Radford    → DALL-E
  ('P12', 'A8', 1)   -- Long Ouyang     → InstructGPT
ON CONFLICT (paper_id, author_id) DO UPDATE SET
  author_order = EXCLUDED.author_order,
  updated_at   = NOW();
