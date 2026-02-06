export const mockData = {
  seed: {
    id: 'attention-2017',
    title: 'Attention Is All You Need',
    authors: 'Vaswani et al.',
    year: 2017,
    citations: 90000,
  },
  references: [
    { id: 'seq2seq-2014', title: 'Sequence to Sequence Learning', year: 2014, citations: 20000, depth: 1 },
    { id: 'bahdanau-2015', title: 'Neural Machine Translation by Jointly Learning to Align', year: 2015, citations: 25000, depth: 1 },
    { id: 'adam-2015', title: 'Adam: A Method for Stochastic Optimization', year: 2015, citations: 80000, depth: 1 },
    { id: 'layernorm-2016', title: 'Layer Normalization', year: 2016, citations: 12000, depth: 1 },
    { id: 'resnet-2016', title: 'Deep Residual Learning', year: 2016, citations: 150000, depth: 1 },
    { id: 'lstm-1997', title: 'Long Short-Term Memory', year: 1997, citations: 70000, depth: 2, parentId: 'seq2seq-2014' },
    { id: 'dropout-2014', title: 'Dropout', year: 2014, citations: 35000, depth: 2, parentId: 'resnet-2016' },
  ],
  citations: [
    { id: 'bert-2018', title: 'BERT: Pre-training of Deep Bidirectional Transformers', year: 2018, citations: 80000, depth: 1 },
    { id: 'gpt2-2019', title: 'Language Models are Unsupervised Multitask Learners', year: 2019, citations: 15000, depth: 1 },
    { id: 'roberta-2019', title: 'RoBERTa: A Robustly Optimized BERT', year: 2019, citations: 12000, depth: 1 },
    { id: 'gpt3-2020', title: 'Language Models are Few-Shot Learners', year: 2020, citations: 25000, depth: 1 },
    { id: 't5-2020', title: 'Exploring Transfer Learning with T5', year: 2020, citations: 10000, depth: 1 },
    { id: 'distilbert-2019', title: 'DistilBERT', year: 2019, citations: 6000, depth: 2, parentId: 'bert-2018' },
    { id: 'chatgpt-2022', title: 'InstructGPT', year: 2022, citations: 5000, depth: 2, parentId: 'gpt3-2020' },
    { id: 'llama-2023', title: 'LLaMA', year: 2023, citations: 8000, depth: 2, parentId: 'gpt3-2020' },
  ],
};
