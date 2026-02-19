-- =============================================================================
-- insert_citations.sql
-- Source: Schema_MLOps.pdf citations table (14 edges)
-- Run AFTER insert_papers.sql
-- Edge cases:
--   P4 cites multiple papers (P1, P3)
--   P1 is cited by multiple papers (P2, P3, P4, P6, P8)
-- =============================================================================

INSERT INTO citations (citing_paper_id, cited_paper_id, citation_context)
VALUES
  ('P2',  'P1', 'BERT builds upon the Transformer architecture introduced in P1.'),
  ('P3',  'P1', 'GPT utilizes the self-attention mechanism from P1.'),
  ('P4',  'P1', 'GPT-3 leverages the Transformer architecture from P1.'),
  ('P4',  'P3', 'GPT-3 is a successor to the original GPT model (P3).'),
  ('P5',  'P2', 'RoBERTa is an optimized version of BERT (P2).'),
  ('P6',  'P1', 'T5 explores transfer learning with a Transformer-based model (P1).'),
  ('P6',  'P2', 'T5 also draws insights from BERT''s pre-training approach (P2).'),
  ('P8',  'P1', 'ViT applies the Transformer architecture (P1) to image recognition.'),
  ('P8',  'P7', 'ViT compares its performance against CNNs like ResNet (P7).'),
  ('P9',  'P4', 'LoRA is a parameter-efficient adaptation method for large language models like GPT-3 (P4).'),
  ('P10', 'P4', 'Chain-of-Thought prompting is demonstrated with large language models such as GPT-3 (P4).'),
  ('P11', 'P4', 'DALL-E leverages large language models like GPT-3 (P4) for text understanding.'),
  ('P11', 'P8', 'DALL-E also incorporates visual understanding similar to ViT (P8).'),
  ('P12', 'P4', 'InstructGPT improves instruction following in large language models like GPT-3 (P4).')
ON CONFLICT (citing_paper_id, cited_paper_id) DO UPDATE SET
  citation_context = EXCLUDED.citation_context,
  updated_at       = NOW();
