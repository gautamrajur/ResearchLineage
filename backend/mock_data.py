"""Mock data for Research Lineage Tracker - based on 'Attention Is All You Need' paper."""

MOCK_DATA = {
    "seed": {
        "paperId": "attention-2017",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"],
        "year": 2017,
        "citationCount": 90000,
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
        "venue": "NeurIPS",
        "url": "https://arxiv.org/abs/1706.03762"
    },
    "references": [
        # Depth 1 - Papers directly cited by the seed paper
        {
            "paperId": "seq2seq-2014",
            "title": "Sequence to Sequence Learning with Neural Networks",
            "authors": ["Ilya Sutskever", "Oriol Vinyals", "Quoc V. Le"],
            "year": 2014,
            "citationCount": 20000,
            "abstract": "Deep Neural Networks (DNNs) are powerful models that have achieved excellent performance on difficult learning tasks.",
            "venue": "NeurIPS",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "bahdanau-2015",
            "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
            "authors": ["Dzmitry Bahdanau", "Kyunghyun Cho", "Yoshua Bengio"],
            "year": 2015,
            "citationCount": 25000,
            "abstract": "Neural machine translation is a recently proposed approach to machine translation that builds a neural network that reads a sentence and outputs a correct translation.",
            "venue": "ICLR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "dropout-2014",
            "title": "Dropout: A Simple Way to Prevent Neural Networks from Overfitting",
            "authors": ["Nitish Srivastava", "Geoffrey Hinton", "Alex Krizhevsky", "Ilya Sutskever", "Ruslan Salakhutdinov"],
            "year": 2014,
            "citationCount": 35000,
            "abstract": "Deep neural nets with a large number of parameters are very powerful machine learning systems. However, overfitting is a serious problem in such networks.",
            "venue": "JMLR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "adam-2015",
            "title": "Adam: A Method for Stochastic Optimization",
            "authors": ["Diederik P. Kingma", "Jimmy Ba"],
            "year": 2015,
            "citationCount": 120000,
            "abstract": "We introduce Adam, an algorithm for first-order gradient-based optimization of stochastic objective functions, based on adaptive estimates of lower-order moments.",
            "venue": "ICLR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "resnet-2016",
            "title": "Deep Residual Learning for Image Recognition",
            "authors": ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
            "year": 2016,
            "citationCount": 150000,
            "abstract": "Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously.",
            "venue": "CVPR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        
        # Depth 2 - Papers cited by depth 1 papers
        {
            "paperId": "lstm-1997",
            "title": "Long Short-Term Memory",
            "authors": ["Sepp Hochreiter", "Jurgen Schmidhuber"],
            "year": 1997,
            "citationCount": 75000,
            "abstract": "Learning to store information over extended time intervals by recurrent backpropagation takes a very long time, mostly because of insufficient, decaying error backflow.",
            "venue": "Neural Computation",
            "depth": 2,
            "parentId": "seq2seq-2014"  # Cited by Seq2Seq
        },
        {
            "paperId": "word2vec-2013",
            "title": "Distributed Representations of Words and Phrases and their Compositionality",
            "authors": ["Tomas Mikolov", "Ilya Sutskever", "Kai Chen", "Greg Corrado", "Jeffrey Dean"],
            "year": 2013,
            "citationCount": 30000,
            "abstract": "The recently introduced continuous Skip-gram model is an efficient method for learning high-quality distributed vector representations that capture a large number of precise syntactic and semantic word relationships.",
            "venue": "NeurIPS",
            "depth": 2,
            "parentId": "seq2seq-2014"  # Cited by Seq2Seq
        },
        {
            "paperId": "batchnorm-2015",
            "title": "Batch Normalization: Accelerating Deep Network Training",
            "authors": ["Sergey Ioffe", "Christian Szegedy"],
            "year": 2015,
            "citationCount": 45000,
            "abstract": "Training Deep Neural Networks is complicated by the fact that the distribution of each layer's inputs changes during training.",
            "venue": "ICML",
            "depth": 2,
            "parentId": "resnet-2016"  # Cited by ResNet
        },
        {
            "paperId": "glorot-init-2010",
            "title": "Understanding the difficulty of training deep feedforward neural networks",
            "authors": ["Xavier Glorot", "Yoshua Bengio"],
            "year": 2010,
            "citationCount": 18000,
            "abstract": "Whereas before 2006 it appears that deep multi-layer neural networks were not successfully trained, since then several algorithms have been shown to successfully train them.",
            "venue": "AISTATS",
            "depth": 2,
            "parentId": "adam-2015"  # Cited by Adam
        },
        
        # Depth 3 - Papers cited by depth 2 papers
        {
            "paperId": "backprop-1986",
            "title": "Learning representations by back-propagating errors",
            "authors": ["David E. Rumelhart", "Geoffrey E. Hinton", "Ronald J. Williams"],
            "year": 1986,
            "citationCount": 35000,
            "abstract": "We describe a new learning procedure, back-propagation, for networks of neurone-like units.",
            "venue": "Nature",
            "depth": 3,
            "parentId": "lstm-1997"  # Cited by LSTM
        }
    ],
    "citations": [
        # Depth 1 - Papers that directly cite the seed paper
        {
            "paperId": "bert-2018",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
            "year": 2018,
            "citationCount": 80000,
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers.",
            "venue": "NAACL",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "gpt2-2019",
            "title": "Language Models are Unsupervised Multitask Learners",
            "authors": ["Alec Radford", "Jeffrey Wu", "Rewon Child", "David Luan", "Dario Amodei", "Ilya Sutskever"],
            "year": 2019,
            "citationCount": 15000,
            "abstract": "Natural language processing tasks, such as question answering, machine translation, reading comprehension, and summarization, are typically approached with supervised learning on task-specific datasets.",
            "venue": "OpenAI",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "vit-2020",
            "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
            "authors": ["Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov", "Dirk Weissenborn", "Xiaohua Zhai", "Thomas Unterthiner", "Mostafa Dehghani", "Matthias Minderer", "Georg Heigold", "Sylvain Gelly"],
            "year": 2020,
            "citationCount": 20000,
            "abstract": "While the Transformer architecture has become the de-facto standard for natural language processing tasks, its applications to computer vision remain limited.",
            "venue": "ICLR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "t5-2020",
            "title": "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer",
            "authors": ["Colin Raffel", "Noam Shazeer", "Adam Roberts", "Katherine Lee", "Sharan Narang", "Michael Matena", "Yanqi Zhou", "Wei Li", "Peter J. Liu"],
            "year": 2020,
            "citationCount": 10000,
            "abstract": "Transfer learning, where a model is first pre-trained on a data-rich task before being fine-tuned on a downstream task, has emerged as a powerful technique in NLP.",
            "venue": "JMLR",
            "depth": 1,
            "parentId": "attention-2017"
        },
        {
            "paperId": "xlnet-2019",
            "title": "XLNet: Generalized Autoregressive Pretraining for Language Understanding",
            "authors": ["Zhilin Yang", "Zihang Dai", "Yiming Yang", "Jaime Carbonell", "Ruslan Salakhutdinov", "Quoc V. Le"],
            "year": 2019,
            "citationCount": 8000,
            "abstract": "With the capability of modeling bidirectional contexts, denoising autoencoding based pretraining like BERT achieves better performance than pretraining approaches based on autoregressive language modeling.",
            "venue": "NeurIPS",
            "depth": 1,
            "parentId": "attention-2017"
        },
        
        # Depth 2 - Papers that cite depth 1 papers
        {
            "paperId": "gpt3-2020",
            "title": "Language Models are Few-Shot Learners",
            "authors": ["Tom Brown", "Benjamin Mann", "Nick Ryder", "Melanie Subbiah", "Jared Kaplan", "Prafulla Dhariwal", "Arvind Neelakantan", "Pranav Shyam", "Girish Sastry", "Amanda Askell"],
            "year": 2020,
            "citationCount": 25000,
            "abstract": "We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.",
            "venue": "NeurIPS",
            "depth": 2,
            "parentId": "gpt2-2019"  # Cites GPT-2
        },
        {
            "paperId": "roberta-2019",
            "title": "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
            "authors": ["Yinhan Liu", "Myle Ott", "Naman Goyal", "Jingfei Du", "Mandar Joshi", "Danqi Chen", "Omer Levy", "Mike Lewis", "Luke Zettlemoyer", "Veselin Stoyanov"],
            "year": 2019,
            "citationCount": 12000,
            "abstract": "Language model pretraining has led to significant performance gains but careful comparison between different approaches is challenging.",
            "venue": "arXiv",
            "depth": 2,
            "parentId": "bert-2018"  # Cites BERT
        },
        {
            "paperId": "swin-2021",
            "title": "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows",
            "authors": ["Ze Liu", "Yutong Lin", "Yue Cao", "Han Hu", "Yixuan Wei", "Zheng Zhang", "Stephen Lin", "Baining Guo"],
            "year": 2021,
            "citationCount": 8000,
            "abstract": "This paper presents a new vision Transformer, called Swin Transformer, that capably serves as a general-purpose backbone for computer vision.",
            "venue": "ICCV",
            "depth": 2,
            "parentId": "vit-2020"  # Cites ViT
        },
        {
            "paperId": "clip-2021",
            "title": "Learning Transferable Visual Models From Natural Language Supervision",
            "authors": ["Alec Radford", "Jong Wook Kim", "Chris Hallacy", "Aditya Ramesh", "Gabriel Goh", "Sandhini Agarwal", "Girish Sastry", "Amanda Askell", "Pamela Mishkin", "Jack Clark"],
            "year": 2021,
            "citationCount": 9000,
            "abstract": "State-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories.",
            "venue": "ICML",
            "depth": 2,
            "parentId": "vit-2020"  # Cites ViT
        },
        
        # Depth 3 - Papers that cite depth 2 papers
        {
            "paperId": "gpt4-2023",
            "title": "GPT-4 Technical Report",
            "authors": ["OpenAI"],
            "year": 2023,
            "citationCount": 5000,
            "abstract": "We report the development of GPT-4, a large-scale, multimodal model which can accept image and text inputs and produce text outputs.",
            "venue": "arXiv",
            "depth": 3,
            "parentId": "gpt3-2020"  # Cites GPT-3
        },
        {
            "paperId": "llama-2023",
            "title": "LLaMA: Open and Efficient Foundation Language Models",
            "authors": ["Hugo Touvron", "Thibaut Lavril", "Gautier Izacard", "Xavier Martinet", "Marie-Anne Lachaux", "Timothee Lacroix", "Baptiste Roziere", "Naman Goyal", "Eric Hambro", "Faisal Azhar"],
            "year": 2023,
            "citationCount": 4000,
            "abstract": "We introduce LLaMA, a collection of foundation language models ranging from 7B to 65B parameters.",
            "venue": "arXiv",
            "depth": 3,
            "parentId": "gpt3-2020"  # Cites GPT-3
        },
        {
            "paperId": "chatgpt-rlhf-2022",
            "title": "Training language models to follow instructions with human feedback",
            "authors": ["Long Ouyang", "Jeff Wu", "Xu Jiang", "Diogo Almeida", "Carroll L. Wainwright", "Pamela Mishkin", "Chong Zhang", "Sandhini Agarwal", "Katarina Slama", "Alex Ray"],
            "year": 2022,
            "citationCount": 6000,
            "abstract": "Making language models bigger does not inherently make them better at following a user's intent.",
            "venue": "NeurIPS",
            "depth": 3,
            "parentId": "gpt3-2020"  # Cites GPT-3
        }
    ]
}


def get_paper(paper_id: str) -> dict | None:
    """Get a paper by ID."""
    if paper_id == MOCK_DATA["seed"]["paperId"]:
        return MOCK_DATA["seed"]

    for paper in MOCK_DATA["references"]:
        if paper["paperId"] == paper_id:
            return paper

    for paper in MOCK_DATA["citations"]:
        if paper["paperId"] == paper_id:
            return paper

    return None


def get_references(paper_id: str, limit: int = 20) -> list[dict]:
    """Get papers that the given paper cites (Pre-Order)."""
    if paper_id == MOCK_DATA["seed"]["paperId"]:
        return MOCK_DATA["references"][:limit]
    return []


def get_citations(paper_id: str, limit: int = 20) -> list[dict]:
    """Get papers that cite the given paper (Post-Order)."""
    if paper_id == MOCK_DATA["seed"]["paperId"]:
        return MOCK_DATA["citations"][:limit]
    return []


def search_papers(query: str) -> list[dict]:
    """Search for papers by title."""
    query = query.lower()
    results = []

    seed = MOCK_DATA["seed"]
    if query in seed["title"].lower():
        results.append(seed)

    for paper in MOCK_DATA["references"] + MOCK_DATA["citations"]:
        if query in paper["title"].lower():
            results.append(paper)

    return results


# ### References view (← pre):
# Backprop (1986) → LSTM (1997) → Seq2Seq (2014) → Attention (2017) SEED
#   depth 3          depth 2         depth 1
  
# Seq2Seq cites LSTM
# LSTM cites Backprop
#   ←────────── Going backwards in time


# ### Citations view (→ post):
# Attention (2017) SEED → BERT (2018) → RoBERTa (2019)
#                         depth 1        depth 2

# BERT cites Attention
# RoBERTa cites BERT
#   ──────────→ Going forward in time

# The Logic:

# Depth = distance from the seed paper
# References: Going backward through what the seed cited, then what those papers cited, etc.
# Citations: Going forward through what cited the seed, then what cited those papers, etc.