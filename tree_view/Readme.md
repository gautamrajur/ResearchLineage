# 🌳 Tree View Component

Interactive research lineage tree showing ancestors (papers cited) and descendants (papers citing) with methodology-focused filtering.

---

## How It Works

### Finding Ancestors (Backward)

**Process:**
1. **Fetch references:** `GET /paper/{paper_id}/references`
2. **Filter:** Keep papers with `intents=['methodology']` (papers used for core approach)
3. **Sort:** By citation count (most influential first)
4. **Select:** Top 3 papers
5. **Recurse:** Repeat for each ancestor (max depth: 2 levels)

**API Call:**
```python
GET /paper/ARXIV:1706.03762/references
Params: {
  'fields': 'citedPaper.paperId,citedPaper.title,citedPaper.year,citedPaper.citationCount,intents,isInfluential',
  'limit': 100
}
```

**Response Sample:**
```json
{
  "data": [{
    "citedPaper": {
      "paperId": "2c03df...",
      "title": "Deep Residual Learning for Image Recognition",
      "year": 2015,
      "citationCount": 217813
    },
    "intents": ["methodology"],
    "isInfluential": true
  }]
}
```

**Result:** 3 ancestors → 9 grandparents (3 per parent)

---

### Finding Descendants (Forward)

**Process:**
1. **Time window:** Search papers published `year+1` to `year+3` (e.g., 2018-2020 for 2017 paper)
2. **Paginate:** Fetch 9,000 papers (Level 0) or 5,000 (Level 1+) via offset
3. **Filter:** Keep papers with `intents=['methodology']` (papers that USED the approach)
4. **Sort:** By citation count
5. **Select:** Top 5 (Level 0) or Top 3 (Level 1+)
6. **Recurse:** Repeat for each descendant with new time window

**Why time window?** Transformer has 162k citations - without filtering by year, we'd only get recent papers (2025-2026) with 0-2 citations. Time window captures influential descendants from immediate post-publication period.

**API Call (with pagination):**
```python
# Batch 1
GET /paper/ARXIV:1706.03762/citations
Params: {
  'fields': 'citingPaper.paperId,citingPaper.title,citingPaper.year,citingPaper.citationCount,intents,isInfluential',
  'limit': 1000,
  'offset': 0,
  'publicationDateOrYear': '2018:2020'
}

# Batch 2
offset=1000

# Batch 3-9
offset=2000, 3000, ...8000

# Total: 9 calls → 9,000 papers
```

**Response Sample:**
```json
{
  "offset": 0,
  "data": [{
    "citingPaper": {
      "paperId": "5c126ae...",
      "title": "Denoising Diffusion Probabilistic Models",
      "year": 2020,
      "citationCount": 26026
    },
    "intents": ["methodology"],
    "isInfluential": false
  }]
}
```

**Result:** 5 descendants → 15 grandchildren (3 per parent)

---

## API Details

**Base URL:** `https://api.semanticscholar.org/graph/v1`

**Endpoints Used:**
- `/paper/{id}` - Get paper metadata
- `/paper/{id}/references` - Get papers this paper cited
- `/paper/{id}/citations` - Get papers that cited this paper

**Key Fields:**

| Field | Description |
|-------|-------------|
| `intents` | Citation intent: `methodology`, `background`, `result` |
| `isInfluential` | Whether citation is marked as influential |
| `citationCount` | Total citations (for sorting) |

**Rate Limits:**
- Free: 100 requests / 5 min (shared)
- With API key: 1 request / second
- Hard limit: `offset + limit < 10,000`

**Our handling:**
- Sleep 1.2s between calls
- Retry on 429 errors (wait 5s, 10s, 15s...)
- Max 10 retries before giving up

---

## Architecture
```python
TreeView.build_tree(paper_id)
│
├─ GET /paper/{id}                    # Target
│
├─ build_recursive_ancestors()        # Backward
│  ├─ GET /paper/{id}/references
│  ├─ Filter: methodology intent
│  ├─ Sort: citation count
│  ├─ Select: top 3
│  └─ Recurse (max depth: 2)
│
└─ build_recursive_descendants()      # Forward  
   ├─ GET /paper/{id}/citations (9 calls, offset 0-8000)
   ├─ Filter: time window + methodology
   ├─ Sort: citation count
   ├─ Select: top 5 (L0) or 3 (L1+)
   └─ Recurse with new time window (max depth: 2)
```

**Total:** ~40 API calls, ~50-60 seconds

---

## Installation
```bash
pip install requests
```

---

## Usage

### Command Line
```bash
# From project root
python src/app.py "https://arxiv.org/abs/1706.03762"

# Or with paper ID
python src/app.py "ARXIV:1706.03762"

# Output: outputs/tree_ARXIV_1706.03762.html
```

### Python API
```python
from tree_view import TreeView, visualize_tree_modern

tree_view = TreeView()
tree = tree_view.build_tree(
    paper_id="ARXIV:1706.03762",
    max_children=5,     # 5 descendants L0, 3 for L1+
    max_depth=2,        # Parents + grandparents
    window_years=3      # Search 3 years after publication
)

visualize_tree_modern(tree, "output.html")
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_children` | 5 | Descendants at L0 (3 for L1+) |
| `max_depth` | 2 | Recursion depth |
| `window_years` | 3 | Years after publication to search |

---

## Output

**Console:** Progress tracking + text tree
**HTML:** Interactive D3.js visualization with:
- Click node → highlight path to target
- Zoom/pan support
- Tooltips on hover
- Color-coded: Blue (ancestors), Red (target), Green (descendants)

**Example:** Transformer → ResNet/Adam (ancestors) | Diffusion/DETR/RAG (descendants)

---

## Limitations

- **API limit:** Max 10k papers per endpoint
- **Time window bias:** May miss papers outside 3-year window
- **Metadata quality:** Some papers have errors ("Et al", "I and J")
- **Node overlap:** Level 2 nodes may overlap (use zoom/pan)

---

## Performance

- **Typical time:** 50-60 seconds for highly-cited papers
- **API calls:** ~40 (1 target + 4 ancestors + 9 desc L0 + 25 desc L1)
- **Papers analyzed:** ~15,000-20,000 (9k L0 + 5k×5 L1)

---

Created by MLOps Group 6 | [GitHub](https://github.com/YashwanthReddy27/MLOps_Grp_6)