-- =============================================================================
-- insert_papers.sql
-- Source: Schema_MLOps.pdf sample data (P1–P12)
-- Run AFTER insert_authors.sql, BEFORE insert_paper_authors.sql
-- =============================================================================

INSERT INTO papers (
  paper_id, title, abstract, venue, year, publication_date,
  citation_count, influential_citation_count, is_open_access,
  source_url, s3_pdf_key
)
VALUES
  (
    'P1',
    'Attention is All You Need',
    'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.',
    'NeurIPS',
    2017,
    '2017-06-12',
    60000, 5000, TRUE,
    'https://proceedings.neurips.cc/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html',
    NULL
  ),
  (
    'P2',
    'BERT: Pre-training of Deep Bidirectional Transformers',
    'We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers.',
    'NAACL',
    2018,
    '2018-10-11',
    45000, 4000, TRUE,
    'https://aclanthology.org/N19-1423/',
    NULL
  ),
  (
    'P3',
    'Generative Pre-trained Transformer (GPT)',
    'Natural language understanding comprises a wide range of diverse tasks such as textual entailment, question answering, semantic similarity assessment, and document classification. Although large unlabeled text corpora are abundant, labeled data for learning these specific tasks is scarce, making it challenging for discriminatively trained models to perform adequately.',
    'OpenAI',
    2018,
    '2018-06-11',
    15000, 1200, TRUE,
    'https://openai.com/blog/language-unsupervised/',
    NULL
  ),
  (
    'P4',
    'Language Models are Few-Shot Learners (GPT-3)',
    'We show that scaling up language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.',
    'NeurIPS',
    2020,
    '2020-05-28',
    25000, 3000, TRUE,
    'https://proceedings.neurips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html',
    NULL
  ),
  (
    'P5',
    'RoBERTa: A Robustly Optimized BERT Pretraining Approach',
    'Language model pretraining has led to significant performance gains but careful comparison between different approaches is challenging. Training is computationally expensive, often done on private datasets of different sizes, and, as we will show, hyperparameter choices have significant impact on the final results.',
    'arXiv',
    2019,
    '2019-07-26',
    18000, 1500, TRUE,
    'https://arxiv.org/abs/1907.11692',
    NULL
  ),
  (
    'P6',
    'T5: Exploring the Limits of Transfer Learning',
    'Transfer learning, where a model is first pre-trained on a data-rich task before being fine-tuned on a downstream task, has emerged as a powerful technique in natural language processing.',
    'JMLR',
    2020,
    '2020-10-15',
    12000, 1000, TRUE,
    'https://www.jmlr.org/papers/volume21/20-074/20-074.pdf',
    NULL
  ),
  (
    'P7',
    'Deep Residual Learning for Image Recognition',
    'Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously.',
    'CVPR',
    2016,
    '2015-12-10',
    120000, 10000, TRUE,
    'https://openaccess.thecvf.com/content_cvpr_2016/html/He_Deep_Residual_Learning_CVPR_2016_paper.html',
    NULL
  ),
  (
    'P8',
    'ViT: An Image is Worth 16x16 Words',
    'We show that this reliance on CNNs is not necessary and a pure transformer applied directly to sequences of image patches can perform very well on image classification tasks.',
    'ICLR',
    2021,
    '2020-10-22',
    10000, 800, TRUE,
    'https://openreview.net/forum?id=YicbFdNTTy',
    NULL
  ),
  (
    'P9',
    'LoRA: Low-Rank Adaptation of Large Language Models',
    'We propose a new method for adapting large language models to downstream tasks, called Low-Rank Adaptation, or LoRA. LoRA reduces the number of trainable parameters by learning pairs of rank-decomposition matrices while keeping the original weights frozen.',
    'ICLR',
    2022,
    '2021-06-17',
    5000, 400, TRUE,
    'https://openreview.net/forum?id=pA-122X-6wZ',
    NULL
  ),
  (
    'P10',
    'Chain-of-Thought Prompting Elicits Reasoning',
    'We explore how generating a chain of thought — a series of intermediate reasoning steps — significantly improves the ability of large language models to perform complex reasoning.',
    'NeurIPS',
    2022,
    '2022-01-28',
    3000, 250, TRUE,
    'https://proceedings.neurips.cc/paper/2022/hash/8bb0d291acd4acf06ef112099c16f326-Abstract.html',
    NULL
  ),
  (
    'P11',
    'Zero-Shot Text-to-Image Generation',
    'Text-to-image generation is a challenging task that has recently received a lot of attention. We present DALL-E, a 12-billion parameter version of GPT-3 trained to generate images from text descriptions.',
    'ICML',
    2021,
    '2021-02-24',
    8000, 700, TRUE,
    'https://proceedings.mlr.press/v139/ramesh21a.html',
    NULL
  ),
  (
    'P12',
    'InstructGPT: Training language models to follow instructions',
    'We describe a new method for training language models to follow instructions with human feedback. We show an avenue for aligning language models with user intent on a wide range of tasks by fine-tuning with human feedback.',
    'OpenAI',
    2022,
    '2022-03-04',
    4000, 350, TRUE,
    'https://openai.com/research/instruction-following',
    NULL
  )
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
