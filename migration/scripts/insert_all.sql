-- =============================================================================
-- ResearchLineage — insert_all.sql (combined)
-- Sample data from Schema_MLOps.pdf: 12 papers, 8 authors, 14 citations
-- FK dependency order respected throughout.
--
-- REVIEW before running:
--   psql "$DB_URL" --set ON_ERROR_STOP=1 -f insert_all.sql
-- =============================================================================

BEGIN;

-- ── 1. authors ────────────────────────────────────────────────────────────────
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

-- ── 2. papers ─────────────────────────────────────────────────────────────────
INSERT INTO papers (
  paper_id, title, abstract, venue, year, publication_date,
  citation_count, influential_citation_count, is_open_access,
  source_url, s3_pdf_key
)
VALUES
  ('P1',  'Attention is All You Need',
   'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.',
   'NeurIPS', 2017, '2017-06-12', 60000, 5000, TRUE,
   'https://proceedings.neurips.cc/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html', NULL),

  ('P2',  'BERT: Pre-training of Deep Bidirectional Transformers',
   'We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers.',
   'NAACL', 2018, '2018-10-11', 45000, 4000, TRUE,
   'https://aclanthology.org/N19-1423/', NULL),

  ('P3',  'Generative Pre-trained Transformer (GPT)',
   'Natural language understanding comprises a wide range of diverse tasks such as textual entailment, question answering, semantic similarity assessment, and document classification.',
   'OpenAI', 2018, '2018-06-11', 15000, 1200, TRUE,
   'https://openai.com/blog/language-unsupervised/', NULL),

  ('P4',  'Language Models are Few-Shot Learners (GPT-3)',
   'We show that scaling up language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.',
   'NeurIPS', 2020, '2020-05-28', 25000, 3000, TRUE,
   'https://proceedings.neurips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html', NULL),

  ('P5',  'RoBERTa: A Robustly Optimized BERT Pretraining Approach',
   'Language model pretraining has led to significant performance gains but careful comparison between different approaches is challenging.',
   'arXiv', 2019, '2019-07-26', 18000, 1500, TRUE,
   'https://arxiv.org/abs/1907.11692', NULL),

  ('P6',  'T5: Exploring the Limits of Transfer Learning',
   'Transfer learning, where a model is first pre-trained on a data-rich task before being fine-tuned on a downstream task, has emerged as a powerful technique in NLP.',
   'JMLR', 2020, '2020-10-15', 12000, 1000, TRUE,
   'https://www.jmlr.org/papers/volume21/20-074/20-074.pdf', NULL),

  ('P7',  'Deep Residual Learning for Image Recognition',
   'Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously.',
   'CVPR', 2016, '2015-12-10', 120000, 10000, TRUE,
   'https://openaccess.thecvf.com/content_cvpr_2016/html/He_Deep_Residual_Learning_CVPR_2016_paper.html', NULL),

  ('P8',  'ViT: An Image is Worth 16x16 Words',
   'We show that this reliance on CNNs is not necessary and a pure transformer applied directly to sequences of image patches can perform very well on image classification tasks.',
   'ICLR', 2021, '2020-10-22', 10000, 800, TRUE,
   'https://openreview.net/forum?id=YicbFdNTTy', NULL),

  ('P9',  'LoRA: Low-Rank Adaptation of Large Language Models',
   'We propose a new method for adapting large language models to downstream tasks called Low-Rank Adaptation, or LoRA.',
   'ICLR', 2022, '2021-06-17', 5000, 400, TRUE,
   'https://openreview.net/forum?id=pA-122X-6wZ', NULL),

  ('P10', 'Chain-of-Thought Prompting Elicits Reasoning',
   'We explore how generating a chain of thought—a series of intermediate reasoning steps—significantly improves the ability of large language models to perform complex reasoning.',
   'NeurIPS', 2022, '2022-01-28', 3000, 250, TRUE,
   'https://proceedings.neurips.cc/paper/2022/hash/8bb0d291acd4acf06ef112099c16f326-Abstract.html', NULL),

  ('P11', 'Zero-Shot Text-to-Image Generation',
   'Text-to-image generation is a challenging task that has recently received a lot of attention.',
   'ICML', 2021, '2021-02-24', 8000, 700, TRUE,
   'https://proceedings.mlr.press/v139/ramesh21a.html', NULL),

  ('P12', 'InstructGPT: Training language models to follow instructions',
   'We describe a new method for training language models to follow instructions with human feedback.',
   'OpenAI', 2022, '2022-03-04', 4000, 350, TRUE,
   'https://openai.com/research/instruction-following', NULL)
ON CONFLICT (paper_id) DO UPDATE SET
  title                       = EXCLUDED.title,
  abstract                    = EXCLUDED.abstract,
  venue                       = EXCLUDED.venue,
  year                        = EXCLUDED.year,
  publication_date            = EXCLUDED.publication_date,
  citation_count              = EXCLUDED.citation_count,
  influential_citation_count  = EXCLUDED.influential_citation_count,
  is_open_access              = EXCLUDED.is_open_access,
  source_url                  = EXCLUDED.source_url,
  updated_at                  = NOW();

-- ── 3. paper_authors ──────────────────────────────────────────────────────────
INSERT INTO paper_authors (paper_id, author_id, author_order)
VALUES
  ('P1',  'A1', 1),
  ('P2',  'A2', 1),
  ('P3',  'A3', 1),
  ('P4',  'A3', 1),
  ('P4',  'A5', 2),
  ('P7',  'A4', 1),
  ('P9',  'A6', 1),
  ('P10', 'A7', 1),
  ('P11', 'A3', 1),
  ('P12', 'A8', 1)
ON CONFLICT (paper_id, author_id) DO UPDATE SET
  author_order = EXCLUDED.author_order,
  updated_at   = NOW();

-- ── 4. citations ──────────────────────────────────────────────────────────────
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

-- ── 5. paper_external_ids ─────────────────────────────────────────────────────
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

-- ── 6. citation_paths ─────────────────────────────────────────────────────────
INSERT INTO citation_paths (path_id, seed_paper_id, max_depth, path_score)
VALUES
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P1', 3, 0.95),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P7', 2, 0.88)
ON CONFLICT (path_id) DO UPDATE SET
  max_depth  = EXCLUDED.max_depth,
  path_score = EXCLUDED.path_score,
  updated_at = NOW();

-- ── 7. citation_path_nodes ────────────────────────────────────────────────────
INSERT INTO citation_path_nodes
  (path_id, paper_id, depth, position, is_influential, influence_reason)
VALUES
  -- Path 1: LLM Evolution
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P1',  0, 1, TRUE,  'Foundational Transformer'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P3',  1, 2, TRUE,  'Early GPT model'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P4',  2, 3, TRUE,  'Scaled-up LLM'),
  ('a1b2c3d4-0001-0000-0000-000000000001', 'P12', 3, 4, FALSE, 'Instruction following'),
  -- Path 2: Vision Transformers
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P7',  0, 1, TRUE,  'Foundational CNN'),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P1',  1, 2, TRUE,  'Transformer architecture'),
  ('a1b2c3d4-0002-0000-0000-000000000002', 'P8',  2, 3, TRUE,  'Vision Transformer application')
ON CONFLICT (path_id, paper_id) DO UPDATE SET
  depth            = EXCLUDED.depth,
  position         = EXCLUDED.position,
  is_influential   = EXCLUDED.is_influential,
  influence_reason = EXCLUDED.influence_reason,
  updated_at       = NOW();

COMMIT;

-- =============================================================================
-- Validation queries (run after commit to verify)
-- =============================================================================
-- SELECT COUNT(*) FROM authors;                -- expect  8
-- SELECT COUNT(*) FROM papers;                 -- expect 12
-- SELECT COUNT(*) FROM paper_authors;          -- expect 10
-- SELECT COUNT(*) FROM citations;              -- expect 14
-- SELECT COUNT(*) FROM paper_external_ids;     -- expect  7
-- SELECT COUNT(*) FROM citation_paths;         -- expect  2
-- SELECT COUNT(*) FROM citation_path_nodes;    -- expect  7
--
-- SELECT * FROM v_papers_with_authors ORDER BY year;
-- SELECT * FROM v_citation_summary    ORDER BY stored_citation_count DESC;
-- SELECT * FROM v_influential_papers  LIMIT 5;
