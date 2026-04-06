# ResearchLineage Backend — Frontend Handoff

## What this is

A FastAPI backend that takes an academic paper ID and returns:
1. **Evolution Timeline** — a linear lineage chain traced backwards via Gemini (which paper led to which)
2. **Predecessor/Successor Tree** — a bidirectional citation tree (ancestors + descendants)

Both results come back in a single API call.

---

## Prerequisites

### 1. Google Cloud authentication

Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install), then:

```bash
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project researchlineage
```

> **Critical**: the last command sets the quota project to `researchlineage`. Without it, the
> Cloud SQL proxy will fail silently with "server closed the connection unexpectedly".

### 2. Cloud SQL Auth Proxy

Download from https://cloud.google.com/sql/docs/postgres/sql-proxy or install via:

```bash
gcloud components install cloud-sql-proxy
```

Start it (keep this terminal open):

```bash
cloud-sql-proxy researchlineage:us-central1:researchlineage-db --port 5432 --address 0.0.0.0
```

You should see:
```
Listening on [::]:5432
The proxy has started successfully and is ready for new connections!
```

### 3. Docker Desktop

Install from https://www.docker.com/products/docker-desktop and make sure it's running.

---

## Running the backend

### Step 1 — Configure environment

```bash
cp src/backend/.env.example src/backend/.env
```

Fill in `GEMINI_API_KEY` (get one free at https://aistudio.google.com). Everything else can stay as-is for local dev.

### Step 2 — Build the image

```bash
docker build -f docker/backend.Dockerfile -t researchlineage-backend:latest .
```

### Step 3 — Run

```bash
docker run --rm \
  --env-file src/backend/.env \
  -e DATABASE_URL="postgresql://jithin:jithin@host.docker.internal:5432/researchlineage?options=-csearch_path%3Ddeployment_schema" \
  -p 8000:8000 \
  researchlineage-backend:latest
```

### Step 4 — Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## API Reference

Interactive docs at **http://localhost:8000/docs** once the container is running.

### `GET /health`

```json
{"status": "ok"}
```

### `POST /analyze`

**Request:**
```json
{
  "paper_id": "1706.03762",
  "max_depth_evolution": 4,
  "max_depth_tree": 2,
  "max_children": 5,
  "window_years": 3
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `paper_id` | string | required | arXiv ID (`1706.03762`), arXiv URL, or Semantic Scholar ID |
| `max_depth_evolution` | int | 6 | How many steps back to trace the lineage chain |
| `max_depth_tree` | int | 2 | Depth of the ancestor/descendant tree |
| `max_children` | int | 5 | Max nodes per level in the tree |
| `window_years` | int | 3 | Years after publication to look for descendants |

**Response:**
```json
{
  "paper_id": "ARXIV:1706.03762",
  "tree": {
    "target": {"paperId": "...", "title": "...", "year": 2017, "citationCount": 171697},
    "ancestors": [
      {
        "paper": {"paperId": "...", "title": "...", "year": 2015, "citationCount": 224535},
        "ancestors": []
      }
    ],
    "descendants": [
      {
        "paper": {"paperId": "...", "title": "...", "year": 2018, "citationCount": 29032},
        "children": []
      }
    ]
  },
  "timeline": {
    "seed_paper": {"paperId": "...", "title": "...", "year": 2017},
    "chain": [
      {
        "paper": {"paperId": "...", "title": "...", "year": 2015, "citationCount": 29146, "abstract": "..."},
        "analysis": {
          "problem_addressed": "...",
          "core_method": "...",
          "key_innovation": "...",
          "breakthrough_level": "revolutionary | major | moderate | minor",
          "explanation_eli5": "...",
          "explanation_intuitive": "...",
          "explanation_technical": "..."
        },
        "comparison": {
          "what_was_improved": "...",
          "how_it_was_improved": "...",
          "why_it_matters": "...",
          "problem_solved_from_predecessor": "..."
        },
        "secondary_influences": [
          {"paper_id": "...", "title": "...", "year": 2014, "contribution": "..."}
        ],
        "source_type": "FULL_TEXT | ABSTRACT_ONLY",
        "is_foundational": false
      }
    ],
    "total_papers": 4,
    "year_range": {"start": 2014, "end": 2017, "span": 3},
    "from_cache": true
  },
  "elapsed": {
    "tree_sec": 2.5,
    "evolution_sec": 3.1,
    "total_sec": 5.6
  }
}
```

### `GET /analyze/{paper_id}`

Same as POST but via GET with query params:
```
GET /analyze/1706.03762?max_depth_evolution=4&max_depth_tree=2&max_children=5&window_years=3
```

---

## Performance

- **Cached paper** (already in DB): ~5–15s total
- **Fresh paper** (first time): 60–300s depending on depth (Gemini + S2 API calls)
- **33,000+ papers** already in cache from prior runs

Set a timeout of at least **600s** on your frontend HTTP client.

---

## Notes

- `timeline` can be `null` if Gemini analysis fails (expired API key, rate limit)
- `tree` is built without Gemini — it should always return
- Paper IDs accepted: `1706.03762`, `ARXIV:1706.03762`, `https://arxiv.org/abs/1706.03762`, or a Semantic Scholar paper ID
