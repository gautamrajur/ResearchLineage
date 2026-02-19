# Phase 3 — Endpoint Analysis: Semantic Scholar Graph API

Base URL: `https://api.semanticscholar.org/graph/v1`

Auth: Optional API key via `x-api-key` header.
Without key: ~1 req/sec. With key: ~10 req/sec.
Apply at: https://www.semanticscholar.org/product/api

---

## Endpoints Used

### 1. GET /paper/{paper_id}

Fetches full metadata for a single paper.

**URL**
```
GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}
    ?fields=paperId,title,abstract,venue,year,publicationDate,
            citationCount,influentialCitationCount,isOpenAccess,
            openAccessPdf,externalIds,url,authors
```

**Path params**
| Param | Description | Example |
|-------|-------------|---------|
| `paper_id` | Semantic Scholar paperId (hex), or `ARXIV:id`, `DOI:id`, `DBLP:key` | `204e3073870fae3d05bcbc2f6a8e263d9b72e776` or `ARXIV:1706.03762` |

**Query params**
| Param | Value | Notes |
|-------|-------|-------|
| `fields` | Comma-separated field names | Must be explicit; default returns only paperId |

**Response schema**
```json
{
  "paperId":                   "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
  "title":                     "Attention Is All You Need",
  "abstract":                  "The dominant sequence transduction models...",
  "venue":                     "Neural Information Processing Systems",
  "year":                      2017,
  "publicationDate":           "2017-06-12",
  "citationCount":             90000,
  "influentialCitationCount":  5000,
  "isOpenAccess":              true,
  "openAccessPdf": {
    "url":    "https://arxiv.org/pdf/1706.03762",
    "status": "GREEN"
  },
  "externalIds": {
    "ArXiv":    "1706.03762",
    "DBLP":     "conf/nips/VaswaniSPUJGKP17",
    "CorpusId": 13756489
  },
  "url": "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
  "authors": [
    { "authorId": "1741101",  "name": "Ashish Vaswani" },
    { "authorId": "1700325",  "name": "Noam Shazeer" }
  ]
}
```

**DB tables populated:** `papers`, `authors`, `paper_authors`, `paper_external_ids`

---

### 2. GET /paper/{paper_id}/references

Papers that the given paper cites (pre-order / ancestors).

**URL**
```
GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references
    ?fields=citedPaper.paperId,citedPaper.title,citedPaper.year,
            citedPaper.citationCount,citedPaper.influentialCitationCount,
            citedPaper.authors,citedPaper.externalIds,citedPaper.venue,
            citedPaper.abstract,citedPaper.isOpenAccess,citedPaper.url,
            citedPaper.publicationDate,isInfluential,intents
    &limit=100
    &offset=0
```

**Query params**
| Param | Default | Max | Notes |
|-------|---------|-----|-------|
| `limit` | 100 | 1000 | Items per page |
| `offset` | 0 | — | Pagination offset |

**Response schema**
```json
{
  "offset": 0,
  "next":   100,
  "data": [
    {
      "isInfluential": true,
      "intents": ["methodology", "background"],
      "citedPaper": {
        "paperId":                  "bc43f72e8ee3a...",
        "title":                    "Sequence to Sequence Learning...",
        "year":                     2014,
        "venue":                    "NIPS",
        "abstract":                 "...",
        "citationCount":            20000,
        "influentialCitationCount": 1800,
        "isOpenAccess":             true,
        "publicationDate":          "2014-09-10",
        "externalIds":              { "ArXiv": "1409.3215" },
        "url":                      "https://www.semanticscholar.org/paper/...",
        "authors": [
          { "authorId": "2066...", "name": "Ilya Sutskever" }
        ]
      }
    }
  ]
}
```

**DB tables populated:** `papers`, `authors`, `paper_authors`, `paper_external_ids`, `citations` (edge: seed → citedPaper maps to `cited_paper_id = citedPaper.paperId`, `citing_paper_id = seed_paper_id`)

---

### 3. GET /paper/{paper_id}/citations

Papers that cite the given paper (post-order / descendants).

**URL**
```
GET https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations
    ?fields=citingPaper.paperId,citingPaper.title,citingPaper.year,
            citingPaper.citationCount,citingPaper.influentialCitationCount,
            citingPaper.authors,citingPaper.externalIds,citingPaper.venue,
            citingPaper.abstract,citingPaper.isOpenAccess,citingPaper.url,
            citingPaper.publicationDate,isInfluential,intents
    &limit=1000
    &offset=0
    &publicationDateOrYear=2018:2020
```

**Additional query params**
| Param | Example | Notes |
|-------|---------|-------|
| `publicationDateOrYear` | `2018:2020` | Filter by year range (used by tree_builder.py windowing) |

**Response schema** — same structure as `/references` but with `citingPaper` instead of `citedPaper`.

**DB tables populated:** `papers`, `authors`, `paper_authors`, `paper_external_ids`, `citations` (edge: `citing_paper_id = citingPaper.paperId`, `cited_paper_id = seed_paper_id`)

---

## Rate Limits

| Tier | Rate | Retry strategy |
|------|------|----------------|
| No key | ~1 req/s | 5s × attempt on 429 (tree_builder.py) |
| API key | ~10 req/s | Same backoff |

The existing `tree_builder.py` already handles 429 with exponential backoff (`5 * attempt` seconds, up to 10 retries).

---

## Known Gaps (fields not available from API)

| DB Column | Reason Not Available |
|-----------|----------------------|
| `papers.s3_pdf_key` | Must be populated after you download and store the PDF |
| `paper_embeddings.embedding` | Must be generated by calling an embedding model (OpenAI, etc.) |
| `paper_sections.*` | Requires PDF parsing (PyMuPDF, pdfplumber, etc.) |

---

## Field Completeness by Endpoint

| Field | `/paper/{id}` | `/references` | `/citations` |
|-------|:---:|:---:|:---:|
| paperId | ✅ | ✅ | ✅ |
| title | ✅ | ✅ | ✅ |
| abstract | ✅ | ✅ | ✅ |
| venue | ✅ | ✅ | ✅ |
| year | ✅ | ✅ | ✅ |
| publicationDate | ✅ | ✅ | ✅ |
| citationCount | ✅ | ✅ | ✅ |
| influentialCitationCount | ✅ | ✅ | ✅ |
| isOpenAccess | ✅ | ✅ | ✅ |
| externalIds | ✅ | ✅ | ✅ |
| authors | ✅ | ✅ | ✅ |
| isInfluential (edge) | — | ✅ | ✅ |
| intents (edge) | — | ✅ | ✅ |
