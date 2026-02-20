"""CLI for fetching research paper PDFs and managing them in GCS."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging  # noqa: E402
for ns in ["httpx", "httpcore", "google", "src", "urllib3"]:
    logging.getLogger(ns).setLevel(logging.WARNING)

from src.storage.gcs_client import GCSClient  # noqa: E402
from src.tasks.data_acquisition import DataAcquisitionTask  # noqa: E402
from src.tasks.pdf_fetcher import PDFFetcher, FetchResult  # noqa: E402

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

async def cmd_upload() -> None:
    """Fetch citation network and upload PDFs to GCS."""
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
        print(f"     Check GOOGLE_APPLICATION_CREDENTIALS and GCS_BUCKET in .env")
        sys.exit(1)

    fetcher = PDFFetcher(gcs)

    header("Configuration")
    print(f"  Paper ID  : {BOLD}{paper_id}{RESET}")
    print(f"  Max depth : {max_depth}")
    print(f"  Direction : {direction}")
    print(f"  GCS dest  : {gcs.base_uri}")

    # Step 1: Data acquisition
    header("Step 1 / 3  ·  Data Acquisition")
    print("  Fetching citation network from Semantic Scholar...\n")

    acq = DataAcquisitionTask()
    try:
        result = await acq.execute(paper_id, max_depth, direction)
    except Exception as e:
        err_msg = str(e)
        if "No papers fetched" in err_msg:
            print(f"  {RED}✗{RESET}  Paper not found: {BOLD}{paper_id}{RESET}")
            print(f"     The paper ID may be invalid or Semantic Scholar may be rate-limiting.")
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

    papers = result["papers"]
    if not papers:
        print(f"  {YELLOW}–{RESET}  No papers discovered. Nothing to fetch.\n")
        return

    print(f"  {GREEN}✓{RESET}  Discovered {BOLD}{len(papers)}{RESET} papers"
          f"  ({result['total_references']} refs, {result['total_citations']} cits)")

    # Step 2 & 3: Resolve + Download + Upload (with GCS dedup)
    header("Step 2 / 3  ·  Resolve PDF URLs + Upload to GCS")
    print("  Checking GCS for existing PDFs, then resolving & uploading...\n")

    async def on_progress(r: FetchResult) -> None:
        print_result(r)

    batch = await fetcher.fetch_batch(papers, on_result=on_progress)

    # Summary
    header("Summary")
    print(f"  {GREEN}Uploaded{RESET}         : {batch.uploaded}")
    print(f"  {BLUE}Already in GCS{RESET}   : {batch.already_in_gcs}")
    print(f"  {RED}Download failed{RESET}  : {batch.download_failed}")
    print(f"  {YELLOW}No open-access PDF found{RESET}    : {batch.no_pdf_found}")
    if batch.errors:
        print(f"  {RED}Errors{RESET}           : {batch.errors}")
    print(f"  {BOLD}Total papers{RESET}     : {batch.total}")
    print(f"  GCS destination  : {gcs.base_uri}")
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
  python temp/pdfs.py [paper_id] [depth] [direction]   Fetch & upload PDFs
  python temp/pdfs.py list                              List PDFs in GCS
  python temp/pdfs.py open  <paper_id or search>        Download & open a PDF
  python temp/pdfs.py delete <paper_id>                 Delete one PDF
  python temp/pdfs.py delete --all                      Delete all PDFs
  python temp/pdfs.py help                              Show this message
""")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd == "help":
        print_usage()
    elif cmd == "list":
        cmd_list()
    elif cmd == "open":
        if len(sys.argv) < 3:
            print("Usage: python temp/pdfs.py open <paper_id or search term>")
            sys.exit(1)
        cmd_open(" ".join(sys.argv[2:]))
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python temp/pdfs.py delete <paper_id | --all>")
            sys.exit(1)
        cmd_delete(sys.argv[2])
    else:
        asyncio.run(cmd_upload())
