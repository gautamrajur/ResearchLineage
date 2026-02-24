"""CLI for fetching research paper PDFs and managing them in GCS."""
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

for ns in ["httpx", "httpcore", "google", "src", "urllib3"]:
    logging.getLogger(ns).setLevel(logging.WARNING)

from typing import Optional, Dict, Any  # noqa: E402

from src.storage.gcs_client import GCSClient  # noqa: E402
from src.tasks.data_acquisition import DataAcquisitionTask  # noqa: E402
from src.tasks.pdf_fetcher import PDFFetcher, FetchResult, BatchResult  # noqa: E402
from src.tasks.pdf_failure_sync import sync_failures_to_db  # noqa: E402
from src.tasks.retry_failed_pdfs import run_retry_failed_pdfs  # noqa: E402
from src.database.connection import DatabaseConnection  # noqa: E402

LOG = logging.getLogger("pdf_fetch")


def _setup_pdf_fetch_log_file(project_root: Path) -> tuple[logging.FileHandler, Path]:
    """Add a log file for the PDF fetch run. Returns (handler, log_path)."""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"pdf_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root = logging.getLogger()
    root.addHandler(fh)
    logging.getLogger("src.tasks.pdf_fetcher").setLevel(logging.INFO)
    logging.getLogger("src.storage.gcs_client").setLevel(logging.INFO)
    LOG.setLevel(logging.INFO)
    LOG.info("PDF fetch log file: %s", log_path)
    return fh, log_path


def _teardown_pdf_fetch_log_file(handler: logging.FileHandler) -> None:
    """Remove the log file handler and close it."""
    root = logging.getLogger()
    root.removeHandler(handler)
    handler.close()


# ── Terminal colours ─────────────────────────────────────────────────
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

STATUS_ICONS = {
    "uploaded": f"{GREEN}↑{RESET}",
    "exists": f"{BLUE}≡{RESET}",
    "no_pdf": f"{YELLOW}–{RESET}",
    "download_failed": f"{RED}✗{RESET}",
    "error": f"{RED}!{RESET}",
}


def header(title: str) -> None:
    print(f"\n{BOLD}{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}{RESET}")


def _log_result(r: FetchResult) -> None:
    """Write one result line to the log file (plain text, no ANSI)."""
    status_label = r.status.upper().replace("_", " ")
    LOG.info("[%s] %s (paper_id=%s)", status_label, r.title, r.paper_id)
    if r.status == "uploaded" and r.size_bytes:
        mb = r.size_bytes / (1024 * 1024)
        LOG.info("  %.1f MB via %s → %s", mb, r.source, r.gcs_uri)
    elif r.status == "download_failed" and r.error:
        LOG.info("  %s", r.error)
    elif r.status == "error" and r.error:
        LOG.info("  Error: %s", r.error)


def print_result(r: FetchResult) -> None:
    icon = STATUS_ICONS.get(r.status, "?")
    print(f"  {icon}  {r.title}")

    if r.status == "uploaded":
        mb = r.size_bytes / (1024 * 1024)
        print(f"       {DIM}{mb:.1f} MB via {r.source} → {r.gcs_uri}{RESET}")
    elif r.status == "exists":
        print(f"       {DIM}Already in GCS{RESET}")
    elif r.status == "no_pdf":
        print(f"       {DIM}No open-access PDF found (tried ArXiv → S2 → Unpaywall){RESET}")
    elif r.status == "download_failed":
        print(f"       {DIM}{r.error}{RESET}")
    elif r.status == "error":
        print(f"       {DIM}Error: {r.error}{RESET}")


# ── Commands ─────────────────────────────────────────────────────────

async def cmd_upload(acquisition_result: Optional[Dict[str, Any]] = None) -> None:
    """
    Fetch citation network and upload PDFs to GCS.

    Args:
        acquisition_result: Pre-fetched paper metadata from DataAcquisitionTask.
                           If provided, skips data acquisition and uses this directly.
                           Expected format:
                           {
                               "target_paper_id": str,
                               "papers": List[Dict],
                               "references": List[Dict],
                               "citations": List[Dict],
                               "total_papers": int,
                               "total_references": int,
                               "total_citations": int,
                               "direction": str,
                           }
    """
    # If acquisition_result is provided, extract paper_id from it
    # Otherwise, get from command line args
    if acquisition_result:
        paper_id = acquisition_result.get("target_paper_id", "unknown")
        max_depth = 0  # Not used when result is pre-provided
        direction = acquisition_result.get("direction", "both")
    else:
        paper_id = sys.argv[1] if len(sys.argv) > 1 else "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
        max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        direction = sys.argv[3] if len(sys.argv) > 3 else "both"

        if direction not in ("backward", "forward", "both"):
            print(f"{RED}Invalid direction '{direction}'. Must be: backward, forward, or both{RESET}")
            sys.exit(1)
        if max_depth < 1 or max_depth > 5:
            print(f"{RED}Invalid depth {max_depth}. Must be between 1 and 5{RESET}")
            sys.exit(1)

    try:
        gcs = GCSClient()
    except Exception as e:
        print(f"\n  {RED}✗{RESET}  GCS connection failed: {e}")
        print(f"     Check Application Default Credentials (e.g. gcloud auth application-default login) and GCS_BUCKET in .env")
        sys.exit(1)

    fetcher = PDFFetcher(gcs)

    project_root = Path(__file__).resolve().parent.parent
    file_handler, log_path = _setup_pdf_fetch_log_file(project_root)
    print(f"  {DIM}Logging to {log_path}{RESET}")

    try:
        await _run_upload(
            paper_id, max_depth, direction, gcs, fetcher,
            acquisition_result=acquisition_result,
        )
    finally:
        _teardown_pdf_fetch_log_file(file_handler)


def _build_failure_list(batch: BatchResult, fetcher: PDFFetcher) -> list:
    """Build list of failure dicts for sync to fetch_pdf_failures table."""
    failure_list = []
    for r in batch.results:
        if r.status not in ("download_failed", "error", "gcs_upload_failed"):
            continue
        failure_list.append({
            "paper_id": r.paper_id,
            "title": r.title,
            "status": r.status,
            "fetch_url": getattr(r, "fetch_url", "") or "",
            "reason": r.error or r.status,
            "timeout_sec": fetcher.download_timeout,
        })
    return failure_list


async def _run_upload(
    paper_id: str, max_depth: int, direction: str,
    gcs: "GCSClient", fetcher: "PDFFetcher",
    acquisition_result: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Run data acquisition and PDF fetch; logs to file and stdout.

    Args:
        paper_id: Target paper ID
        max_depth: Maximum depth for citation network traversal
        direction: "backward", "forward", or "both"
        gcs: GCS client instance
        fetcher: PDF fetcher instance
        acquisition_result: Pre-fetched paper metadata. If provided, skips
                           DataAcquisitionTask and uses this data directly.
    """
    header("Configuration")
    LOG.info("paper_id=%s max_depth=%s direction=%s gcs=%s", paper_id, max_depth, direction, gcs.base_uri)
    print(f"  Paper ID  : {BOLD}{paper_id}{RESET}")
    print(f"  Max depth : {max_depth}")
    print(f"  Direction : {direction}")
    print(f"  GCS dest  : {gcs.base_uri}")

    # Step 1: Data acquisition (conditionally skip if result provided)
    header("Step 1 / 3  ·  Data Acquisition")

    if acquisition_result is not None and acquisition_result.get("papers"):
        # Validate acquisition_result structure
        required_keys = ["papers", "target_paper_id", "total_references", "total_citations"]
        missing_keys = [k for k in required_keys if k not in acquisition_result]
        if missing_keys:
            err_msg = f"acquisition_result missing required keys: {missing_keys}"
            LOG.error(err_msg)
            print(f"  {RED}✗{RESET}  {err_msg}")
            print()
            sys.exit(1)

        # Use pre-provided acquisition result (from DAG pipeline)
        print("  Using pre-fetched paper metadata (skipping API calls)...\n")
        LOG.info(
            "Using pre-provided acquisition_result with %d papers",
            len(acquisition_result.get("papers", [])),
        )
        result = acquisition_result
    else:
        # Run DataAcquisitionTask (CLI flow)
        print("  Fetching citation network from Semantic Scholar...\n")

        acq = DataAcquisitionTask()
        try:
            result = await acq.execute(paper_id, max_depth, direction)
        except Exception as e:
            err_msg = str(e)
            LOG.error("Data acquisition failed: %s", err_msg)
            if "No papers fetched" in err_msg:
                if "429" in err_msg or "Rate limit" in err_msg:
                    print(f"  {RED}✗{RESET}  Rate limit exceeded.")
                    print(f"     Try again in a few minutes.")
                else:
                    print(f"  {RED}✗{RESET}  Paper not found: {BOLD}{paper_id}{RESET}")
                    print(f"     The paper ID may be invalid or not in Semantic Scholar.")
                    print(f"     Verify at: https://api.semanticscholar.org/graph/v1/paper/{paper_id}")
            elif "Invalid paper_id" in err_msg:
                print(f"  {RED}✗{RESET}  Invalid paper ID format: {BOLD}{paper_id}{RESET}")
            elif "Invalid direction" in err_msg or "Invalid max_depth" in err_msg:
                print(f"  {RED}✗{RESET}  {err_msg}")
            else:
                print(f"  {RED}✗{RESET}  Data acquisition failed: {err_msg}")
            print()
            sys.exit(1)
        finally:
            await acq.close()

    # From here, the flow is identical regardless of data source
    papers = result["papers"]
    if not papers:
        LOG.info("No papers discovered; nothing to fetch")
        print(f"  {YELLOW}–{RESET}  No papers discovered. Nothing to fetch.\n")
        return

    print(f"  {GREEN}✓{RESET}  Discovered {BOLD}{len(papers)}{RESET} papers"
          f"  ({result['total_references']} refs, {result['total_citations']} cits)")
    LOG.info("Discovered %d papers (%s refs, %s cits)", len(papers), result["total_references"], result["total_citations"])

    # Step 2 & 3: Resolve + Download + Upload (with GCS dedup)
    header("Step 2 / 3  ·  Resolve PDF URLs + Upload to GCS")
    print("  Checking GCS for existing PDFs, then resolving & uploading...\n")
    LOG.info("Starting PDF fetch batch (GCS dedup, then resolve + download + upload)")

    async def on_progress(r: FetchResult) -> None:
        _log_result(r)
        print_result(r)

    start_time = time.perf_counter()
    batch = await fetcher.fetch_batch(papers, on_result=on_progress)
    elapsed = time.perf_counter() - start_time

    # Summary
    header("Summary")
    print(f"  {GREEN}Uploaded{RESET}                    : {batch.uploaded}")
    print(f"  {BLUE}Already in GCS{RESET}              : {batch.already_in_gcs}")
    print(f"  {RED}Download failed{RESET}             : {batch.download_failed}")
    print(f"  {YELLOW}No open-access PDF found{RESET}    : {batch.no_pdf_found}")
    if batch.errors:
        print(f"  {RED}Errors{RESET}                      : {batch.errors}")
    print(f"  {BOLD}Total papers{RESET}                : {batch.total}")
    if elapsed >= 60:
        mins, secs = divmod(int(round(elapsed)), 60)
        print(f"  {BOLD}Total time taken{RESET}            : {mins}m {secs}s")
    else:
        print(f"  {BOLD}Total time taken{RESET}            : {elapsed:.1f}s")
    print(f"  GCS destination  : {gcs.base_uri}")
    print()

    LOG.info(
        "Summary: uploaded=%d already_in_gcs=%d download_failed=%d no_pdf_found=%d errors=%d total=%d time=%.1fs",
        batch.uploaded, batch.already_in_gcs, batch.download_failed, batch.no_pdf_found, batch.errors, batch.total, elapsed,
    )
    # Consolidated failure details for Download failed, Errors, and GCS upload failed
    failed = [r for r in batch.results if r.status == "download_failed"]
    errored = [r for r in batch.results if r.status == "error"]
    gcs_failed = [r for r in batch.results if r.status == "gcs_upload_failed"]
    if failed or errored or gcs_failed:
        LOG.info("--- Failure details ---")
        for r in failed:
            LOG.info(
                "[DOWNLOAD_FAILED] paper_id=%s title=%s error=%s",
                r.paper_id, r.title, (r.error or "(no message)"),
            )
        for r in errored:
            LOG.info(
                "[ERROR] paper_id=%s title=%s error=%s",
                r.paper_id, r.title, (r.error or "(no message)"),
            )
        for r in gcs_failed:
            LOG.info(
                "[GCS_UPLOAD_FAILED] paper_id=%s title=%s error=%s",
                r.paper_id, r.title, (r.error or "(no message)"),
            )
        LOG.info(
            "--- End failure details (%d download_failed, %d errors, %d gcs_upload_failed) ---",
            len(failed), len(errored), len(gcs_failed),
        )

    # Sync failures to fetch_pdf_failures table (for retry flow / DAG)
    failure_list = _build_failure_list(batch, fetcher)
    if failure_list:
        try:
            db = DatabaseConnection()
            synced = sync_failures_to_db(failure_list, db.get_session)
            LOG.info("Synced %d failure(s) to fetch_pdf_failures", synced)
        except Exception as e:
            LOG.warning("Could not sync failures to database (table may not exist or DB not configured): %s", e)


async def cmd_retry_failures() -> None:
    """Run retry for failed PDFs from fetch_pdf_failures table (eligible rows only)."""
    try:
        gcs = GCSClient()
        db = DatabaseConnection()
    except Exception as e:
        print(f"\n  {RED}✗{RESET}  Setup failed: {e}")
        sys.exit(1)
    header("Retry failed PDFs")
    print("  Querying fetch_pdf_failures for eligible rows, then fetching with stored URL/timeout...\n")
    stats = await run_retry_failed_pdfs(db.get_session, gcs)
    print(f"  Fetched (eligible) : {stats['fetched']}")
    print(f"  Succeeded          : {stats['succeeded']}")
    print(f"  Failed             : {stats['failed']}")
    print(f"  Deleted (403/404)  : {stats['deleted_403_404']}")
    print(f"  Reconciled (GCS)   : {stats['reconciled']}")
    print(f"  Alerted            : {stats['alerted']}")
    print()


def cmd_list() -> None:
    """List all PDFs in GCS."""
    gcs = GCSClient()
    files = gcs.list_files()

    if not files:
        print("No PDFs found in GCS.")
        return

    header(f"PDFs in {gcs.base_uri}")
    print(f"\n  {'#':<4} {'Filename':<50} {'Size':>8}  {'Uploaded'}")
    print(f"  {'─'*4} {'─'*50} {'─'*8}  {'─'*19}")

    for i, f in enumerate(files, 1):
        print(f"  {i:<4} {f['filename']:<50} {f['size_mb']:>6.1f} MB  {f['uploaded']}")

    print(f"\n  Total: {BOLD}{len(files)}{RESET} files\n")


def cmd_open(search: str) -> None:
    """Fetch a specific PDF from GCS and open it."""
    gcs = GCSClient()

    if not search.endswith(".pdf"):
        files = gcs.list_files()
        matches = [f for f in files if search.lower() in f["filename"].lower()]
        if not matches:
            print(f"No PDF matching '{search}' found in GCS.")
            return
        if len(matches) > 1:
            print(f"Multiple matches for '{search}':")
            for m in matches:
                print(f"  - {m['filename']}")
            print("\nPlease be more specific.")
            return
        search = matches[0]["filename"]

    print(f"Fetching: {search}")
    path = gcs.open_locally(search)
    if path:
        print(f"Opened: {path}")
    else:
        print(f"File not found: {search}")


def cmd_delete(target: str) -> None:
    """Delete a specific file or all files from GCS."""
    gcs = GCSClient()

    if target == "--all":
        files = gcs.list_files()
        if not files:
            print("No files to delete.")
            return
        confirm = input(f"Delete ALL {len(files)} PDFs in {gcs.base_uri}? [y/N]: ")
        if confirm.strip().lower() == "y":
            count = gcs.delete_all()
            print(f"Deleted {count} files.")
        else:
            print("Cancelled.")
        return

    filename = target if target.endswith(".pdf") else f"{target}.pdf"
    if gcs.delete(filename):
        print(f"Deleted: {gcs.base_uri}{filename}")
    else:
        print(f"File not found: {filename}")


def print_usage() -> None:
    print(f"""
{BOLD}Usage:{RESET}
  python scripts/cli/pdfs.py [paper_id] [depth] [direction]   Fetch & upload PDFs
  python scripts/cli/pdfs.py list                              List PDFs in GCS
  python scripts/cli/pdfs.py open  <paper_id or search>        Download & open a PDF
  python scripts/cli/pdfs.py delete <paper_id>                 Delete one PDF
  python scripts/cli/pdfs.py delete --all                      Delete all PDFs
  python scripts/cli/pdfs.py retry-failures                    Retry failed PDFs from DB
  python scripts/cli/pdfs.py help                              Show this message
""")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd == "help":
        print_usage()
    elif cmd == "list":
        cmd_list()
    elif cmd == "open":
        if len(sys.argv) < 3:
            print("Usage: python scripts/cli/pdfs.py open <paper_id or search term>")
            sys.exit(1)
        cmd_open(" ".join(sys.argv[2:]))
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python scripts/cli/pdfs.py delete <paper_id | --all>")
            sys.exit(1)
        cmd_delete(sys.argv[2])
    elif cmd == "retry-failures":
        asyncio.run(cmd_retry_failures())
    else:
        asyncio.run(cmd_upload())
