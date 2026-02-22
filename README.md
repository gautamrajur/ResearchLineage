# ResearchLineage

LLM Powered Research Lineage and Path Tracker — enables users to research in the fastest time possible.

We're not replacing comprehensive literature reviews or deep reading (that's impossible!). We're the Wikipedia of research lineages, a starting point that helps researchers get oriented 10x faster, so they can read the right papers in the right order with the right context. Researchers don't need another tool that replaces reading. They need a tool that makes reading more strategic. We provide the map before the journey.

---

## Database operations for PDF failure handling

Failed PDF fetches are stored in a PostgreSQL table so they can be retried later and, when failures persist, surfaced via email alerts. This section describes the database operations, what you need to run them, and how to run the retry flow.

### Purpose of the failure table

- Only **failed** PDF fetches (download_failed or error) are written to the database. Successful uploads and 403/404 responses do not create or keep rows.
- Each row represents one paper that failed: `paper_id`, `title`, `status`, `fail_runs`, `fetch_url`, `reason`, `timeout_sec`, `retry_after`, `first_failed_at`, `last_attempt_at`, `alerted`, `created_at`.
- **fail_runs** is the number of **runs** (not in-run retries) in which that paper failed. It increments each time the sync or retry flow records a failure for that paper.
- Rows are **deleted** when the paper later succeeds or when the failure is 403/404 (no point retrying). They are also deleted during retry if the paper already has a PDF in GCS (reconciliation).

### Operations

| Operation | Purpose |
|-----------|---------|
| **Sync to DB** | After each main PDF fetch run, the list of failed papers (download_failed / error) is upserted into `fetch_pdf_failures`: new paper_id → insert with fail_runs=1 and retry_after = NOW() + 30s; existing paper_id → increment fail_runs, update reason/fetch_url/timeout_sec, set last_attempt_at and retry_after = NOW() + 30s. |
| **Retry failed PDFs** | A dedicated command reads rows where `retry_after` has passed and `alerted = FALSE`, re-fetches each PDF using the stored URL and timeout, then updates the table: delete row on success or 403/404; on other failure, increment fail_runs and bump timeout_sec by 20s, set retry_after = NOW() + 30s. |
| **GCS reconciliation** | During retry, any row whose paper_id already has a PDF in GCS is deleted so the table does not keep retrying papers that are already in storage. |
| **Alerts** | After retry (or when retry runs with no eligible rows but there are pending alerts), any row with `fail_runs > 5` and `alerted = FALSE` triggers an alert: if SMTP is configured, an HTML email is sent with a table of those papers, then those rows are set to `alerted = TRUE`; otherwise the same information is only logged. |

### What you need to run error-free

- **PostgreSQL**: Create the `fetch_pdf_failures` table in your database (the app does not run migrations). Columns and indexes are implied by `src/database/fetch_pdf_failures_repository.py`; an index on `retry_after` is recommended for the eligible-for-retry query.
- **`.env`** in the project root with at least:
  - **Database**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`. Used by the connection pool and by the failure repository.
  - **Optional — Email alerts**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO`. If `SMTP_HOST` and `ALERT_EMAIL_TO` are set, alerts are sent; otherwise they are only logged.

Do not commit `.env`; it is listed in `.gitignore`.

### Environment variables (DB and alerts)

| Variable | Required | Purpose |
|----------|----------|---------|
| `POSTGRES_USER` | Yes | PostgreSQL user. |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password. |
| `POSTGRES_HOST` | Yes | PostgreSQL host (e.g. `localhost` or Cloud SQL proxy). |
| `POSTGRES_PORT` | Yes | PostgreSQL port (e.g. `5432`). |
| `POSTGRES_DB` | Yes | Database name (e.g. `researchlineage`). |
| `SMTP_HOST` | No | SMTP server host; required only to send alert emails. |
| `SMTP_PORT` | No | SMTP port (default 587). |
| `SMTP_USER` | No | SMTP username. |
| `SMTP_PASSWORD` | No | SMTP password or app password. |
| `ALERT_EMAIL_FROM` | No | Sender address in alert emails. |
| `ALERT_EMAIL_TO` | No | Recipient(s), comma-separated; required for sending alerts. |

### Running the retry flow

From the project root:

```bash
python temp/pdfs.py retry-failures
```

This will:

1. Query `fetch_pdf_failures` for rows where `retry_after` has passed and `alerted = FALSE`.
2. For each such row, attempt to fetch the PDF from the stored URL with the stored timeout and upload to GCS.
3. Update the table: delete row on success or 403/404; otherwise update fail_runs, timeout, retry_after.
4. Reconcile with GCS (delete rows whose paper_id already has a PDF in GCS).
5. For any row with `fail_runs > 5` and `alerted = FALSE`, send an HTML alert email (if SMTP is configured) and set `alerted = TRUE`.

The main PDF fetch run (e.g. `python temp/pdfs.py ...`) syncs failures to the same table after each run; no separate command is needed for that.

### Verifying the database

To check that the database is reachable and the table exists:

```bash
python scripts/check_fetch_pdf_failures_db.py
```

This uses `POSTGRES_*` from `.env` and prints the row count of `fetch_pdf_failures`.
