# ResearchLineage

LLM Powered Research Lineage and Path Tracker — enables users to research in the fastest time possible.

We're not replacing comprehensive literature reviews or deep reading (that's impossible!). We're the Wikipedia of research lineages, a starting point that helps researchers get oriented 10x faster, so they can read the right papers in the right order with the right context. Researchers don't need another tool that replaces reading. They need a tool that makes reading more strategic. We provide the map before the journey.

---

## PDF Fetching

The project can fetch open-access PDFs for papers discovered by the data acquisition pipeline, store them in **Google Cloud Storage (GCS)**, and expose a CLI to run the workflow, list/open/delete files, and inspect results.

### How it works

1. **Data acquisition** (Semantic Scholar / OpenAlex) fetches the citation network from a seed paper and returns a list of **papers** (each with `paperId`, title, `externalIds` such as ArXiv/DOI, etc.).
2. **PDF step** takes that list and, for each paper:
   - Checks if a PDF already exists in GCS (by `paper_id.pdf`) and skips download if so.
   - **Resolves** a PDF URL using a 3-step fallback: **ArXiv** (if ArXiv ID exists) → **Semantic Scholar** `openAccessPdf` → **Unpaywall** (by DOI).
   - **Downloads** the PDF (with retries and timeout), **validates** it (size and `%PDF-` header), and **uploads** it to GCS with metadata (e.g. `arxiv_id`, `file_name`, `published_year`/`month`).
3. All PDFs in GCS are named **`paper_id.pdf`** for consistent lookup and deduplication.

### Workflow and CLI

- **Fetch and upload PDFs**  
  `python temp/pdfs.py [paper_id] [depth] [direction]`  
  Runs data acquisition for the given seed paper (and depth/direction), then resolves, downloads, and uploads PDFs to GCS.

- **List PDFs in GCS**  
  `python temp/pdfs.py list`

- **Open a PDF locally**  
  `python temp/pdfs.py open <paper_id or search term>`  
  Downloads the file from GCS and opens it with the system default viewer.

- **Delete PDFs**  
  `python temp/pdfs.py delete <paper_id>` or `python temp/pdfs.py delete --all`

- **Help**  
  `python temp/pdfs.py help`

Configuration (paper_id, depth, direction, GCS destination) is printed at startup. The run ends with a **summary**: uploaded count, already in GCS, download failed, no open-access PDF found, errors, total papers, total time taken, and GCS destination.

### Script variations and what they do

**Base command:** `python temp/pdfs.py [command] [arguments]`

| Variation | Command | What it does |
|-----------|---------|--------------|
| **Fetch & upload (defaults)** | `python temp/pdfs.py` | Uses default seed paper (`204e3073870fae3d05bcbc2f6a8e263d9b72e776`), depth `1`, direction `both`. Runs data acquisition then PDF fetch/upload to GCS. |
| **Fetch with custom seed** | `python temp/pdfs.py <paper_id>` | Same as above but starts from the given Semantic Scholar `paper_id` (e.g. another paper's ID). |
| **Fetch with depth** | `python temp/pdfs.py <paper_id> <depth>` | `depth` = how many levels of references/citations to follow (1–5). Deeper = more papers, longer run. |
| **Fetch with direction** | `python temp/pdfs.py <paper_id> <depth> <direction>` | `direction`: `backward` (references only), `forward` (citations only), or `both`. Controls which part of the citation network is fetched before PDFs. |
| **List PDFs** | `python temp/pdfs.py list` | Lists all PDFs in the configured GCS bucket/prefix (filename, size, uploaded time). |
| **Open one PDF** | `python temp/pdfs.py open <paper_id_or_search>` | Downloads the PDF from GCS and opens it locally. Use full `paper_id` or a search term that matches the filename; if multiple match, you're asked to be more specific. |
| **Delete one PDF** | `python temp/pdfs.py delete <paper_id>` | Deletes `paper_id.pdf` from GCS. You can pass `paper_id` with or without the `.pdf` suffix. |
| **Delete all PDFs** | `python temp/pdfs.py delete --all` | Prompts for confirmation, then deletes every PDF under the configured GCS prefix. |
| **Help** | `python temp/pdfs.py help` | Prints usage and the list of commands/variations. |

**Parameter summary (upload mode)**

- **`paper_id`** — Semantic Scholar paper ID of the seed paper (optional; default is the "Attention is All You Need" paper).
- **`depth`** — Recursion depth for references/citations (1–5). Optional; default `1`.
- **`direction`** — `backward` \| `forward` \| `both`. Optional; default `both`.

**Examples**

```bash
# Default run (default paper, depth 1, both directions)
python temp/pdfs.py

# Custom seed, depth 2, both directions
python temp/pdfs.py 204e3073870fae3d05bcbc2f6a8e263d9b72e776 2 both

# Only references (backward), depth 1
python temp/pdfs.py 204e3073870fae3d05bcbc2f6a8e263d9b72e776 1 backward

# Only citations (forward)
python temp/pdfs.py 204e3073870fae3d05bcbc2f6a8e263d9b72e776 1 forward

# Open a PDF
python temp/pdfs.py open 204e3073870fae3d05bcbc2f6a8e263d9b72e776
python temp/pdfs.py open Attention

# Delete one PDF
python temp/pdfs.py delete 204e3073870fae3d05bcbc2f6a8e263d9b72e776
```

### Failures and what we do

- **No open-access PDF found**  
  No URL could be resolved from ArXiv, Semantic Scholar, or Unpaywall. We count these and report them; no retry within the same run.

- **Download failed**  
  A URL was found but the download failed (e.g. HTTP non-200, timeout, invalid or non-PDF content). We retry up to **3 times** with a short delay; if all fail, we count the paper as "download failed" and continue.

- **Errors**  
  Any other exception (e.g. GCS upload failure, network error). We catch it per paper, count it, and continue the batch.

- **Data acquisition failures**  
  Invalid paper_id, 404 from the API, or "No papers fetched" are caught; we print a clear message (and suggest verifying the paper ID) and exit without a stack trace.

- **Empty or invalid input**  
  Empty paper list, missing `paperId`, invalid direction/depth, and GCS connection failures are validated up front; we exit or skip with clear messages.

### Optimizations

- **GCS deduplication**  
  Before resolving any URLs, we call **`exists_batch`** for all `paper_id.pdf` names in one request and skip papers that already exist in GCS.

- **Concurrency**  
  PDF resolution and download run **asynchronously** (asyncio) with a **semaphore** (default concurrency 7) so many papers are processed in parallel without overloading APIs or the network.

- **Single GCS client**  
  The underlying `google.cloud.storage` client is a **singleton** shared across all GCS operations to avoid repeated auth and connection setup.

- **GCS I/O off the event loop**  
  Synchronous GCS calls (upload, exists_batch, etc.) are run via **`asyncio.to_thread`** so they don't block the async event loop.

### Error handling and edge cases

- **Retries**  
  PDF URL resolution (Semantic Scholar, Unpaywall) and PDF download use **3 retries** with a configurable delay (e.g. 30 ms). Rate limits (429) trigger a wait and retry.

- **Validation**  
  Direction must be `backward` \| `forward` \| `both`; depth 1–5; paper_id non-empty. GCS bucket/prefix and credentials (ADC) are checked at startup where possible.

- **Per-paper isolation**  
  One paper failing (download_failed or error) does not stop the batch; results are collected and reported in the summary and in logs.

- **Missing paperId / empty papers**  
  Papers without `paperId` are skipped or reported as error; an empty paper list after data acquisition is handled without crashing.

- **GCS `exists_batch` failure**  
  If the batch existence check fails, we log a warning and proceed without deduplication (treat as if no files exist) so the run can continue.

### Logging and tracking

- **Log file**  
  Each upload run writes to a timestamped log under **`logs/pdf_fetch_YYYYMMDD_HHMMSS.log`**. The path is printed at startup (e.g. "Logging to …").

- **What's logged**  
  - Configuration (paper_id, depth, direction, GCS base URI)  
  - Data acquisition result (e.g. "Discovered N papers") or failure  
  - **Per paper:** API resolution (arxiv=found \| no_id, semantic_scholar=found \| not_found, unpaywall=found \| not_found \| no_doi, no_pdf_from_any_source)  
  - **Download failures:** `pdf_download_failed` with `url`, `status_code` or `reason=invalid_content` or `reason=exception` and `error`  
  - Per-paper result line: status (UPLOADED, EXISTS, NO_PDF, DOWNLOAD_FAILED, ERROR), title, paper_id, and for failures the error message  
  - Summary counts and total time  
  - **Failure details:** a consolidated block listing every **Download failed** and **Error** with paper_id, title, and full error message for easier inspection.

- **Stdout**  
  The same run also prints progress and summary to the terminal (with colours and icons). Logger level for third-party libs (e.g. httpx, google) is set to WARNING to reduce noise.

### Environment and dependencies

- **GCS**  
  Uses **Application Default Credentials (ADC)** by default (e.g. `gcloud auth application-default login`). Optional env: `GCS_BUCKET`, `GCS_PREFIX` (see `.env.example`). Do not set `GOOGLE_APPLICATION_CREDENTIALS` when using ADC.

- **Redis**  
  Optional. If available, the data acquisition step uses it to cache API responses; if Redis is down, caching is disabled and the pipeline still runs.

- **Python**  
  See `requirements.txt` (includes `google-cloud-storage`, `httpx`, etc.). Run from project root so `src` and `temp` are importable.
