"""
gcs_upload.py - Upload pipeline outputs to Google Cloud Storage

Usage:
    python gcs_upload.py                          # Upload everything
    python gcs_upload.py --sync                   # Only upload new files
    python gcs_upload.py --training-only          # Just training data
    python gcs_upload.py --logs-only              # Just logs
    python gcs_upload.py --timelines-only         # Just timelines
    python gcs_upload.py --list                   # See bucket contents
    python gcs_upload.py --bucket other-bucket    # Different bucket
    python gcs_upload.py --project other-project  # Different GCP project
"""

import argparse
import os
from datetime import datetime

from google.cloud import storage
from config import (
    TRAINING_DATA_FILE, TIMELINE_OUTPUT_DIR,
    OUTPUT_DIR, logger
)

print = logger.info

# ========================================
# Defaults (override via CLI args)
# ========================================

DEFAULT_BUCKET = "researchlineage-data"
DEFAULT_PROJECT = "mlops-researchlineage"
LOG_DIR = "logs"


# ========================================
# Upload Functions
# ========================================

def get_client(project=DEFAULT_PROJECT):
    """Create GCS client."""
    return storage.Client(project=project)


def upload_file(client, bucket_name, local_path, gcs_path, sync=False):
    """
    Upload a single file to GCS.
    If sync=True, skips upload if file already exists in bucket.
    """
    if not os.path.exists(local_path):
        print(f"  ⚠️  File not found: {local_path}")
        return False

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    if sync and blob.exists():
        return False

    blob.upload_from_filename(local_path)

    size_kb = os.path.getsize(local_path) / 1024
    print(f"  ✅ Uploaded: {local_path} → gs://{bucket_name}/{gcs_path} ({size_kb:.1f} KB)")
    return True


def upload_directory(client, bucket_name, local_dir, gcs_prefix, sync=False):
    """
    Upload all files in a directory to GCS.
    If sync=True, only uploads new files.
    """
    if not os.path.exists(local_dir):
        print(f"  ⚠️  Directory not found: {local_dir}")
        return 0, 0

    uploaded = 0
    skipped = 0
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_dir)
            gcs_path = f"{gcs_prefix}/{relative_path}".replace("\\", "/")

            if upload_file(client, bucket_name, local_path, gcs_path, sync=sync):
                uploaded += 1
            else:
                skipped += 1

    return uploaded, skipped


# ========================================
# High-Level Upload Functions
# ========================================

def upload_training_data(client, bucket_name, sync=False):
    """Upload training data JSONL with unique timestamp to avoid overwriting."""
    print("")
    print("📤 Uploading training data...")

    if not os.path.exists(TRAINING_DATA_FILE):
        print("  ⚠️  No training data found.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    gcs_name = f"training_data/lineage_training_data_{ts}.jsonl"

    upload_file(client, bucket_name, TRAINING_DATA_FILE, gcs_name, sync=False)


def upload_timelines(client, bucket_name, sync=False):
    """Upload all timeline JSON files."""
    print("")
    print("📤 Uploading timelines...")

    uploaded, skipped = upload_directory(client, bucket_name,
                                         TIMELINE_OUTPUT_DIR, "timelines", sync=sync)
    print(f"  📊 Uploaded {uploaded}, skipped {skipped} (unchanged)")


def upload_logs(client, bucket_name, sync=False):
    """Upload all log files."""
    print("")
    print("📤 Uploading logs...")

    uploaded, skipped = upload_directory(client, bucket_name,
                                         LOG_DIR, "logs", sync=sync)
    print(f"  📊 Uploaded {uploaded}, skipped {skipped} (unchanged)")


def upload_all(client, bucket_name, sync=False):
    """Upload everything."""
    upload_training_data(client, bucket_name, sync=sync)
    upload_timelines(client, bucket_name, sync=sync)
    upload_logs(client, bucket_name, sync=sync)


# ========================================
# List bucket contents
# ========================================

def list_bucket(client, bucket_name):
    """List all files currently in the bucket."""
    print("")
    print(f"📦 Contents of gs://{bucket_name}/")

    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs())

    if not blobs:
        print("  (empty)")
        return

    total_size = 0
    for blob in blobs:
        size_kb = blob.size / 1024 if blob.size else 0
        total_size += blob.size or 0
        print(f"  {blob.name:60s} {size_kb:>8.1f} KB")

    print(f"  {'─' * 70}")
    print(f"  Total: {len(blobs)} files, {total_size / (1024*1024):.2f} MB")


# ========================================
# CLI
# ========================================

def main():
    parser = argparse.ArgumentParser(description="Upload pipeline outputs to GCS")
    parser.add_argument("--bucket", type=str, default=DEFAULT_BUCKET,
                        help=f"GCS bucket name (default: {DEFAULT_BUCKET})")
    parser.add_argument("--project", type=str, default=DEFAULT_PROJECT,
                        help=f"GCP project ID (default: {DEFAULT_PROJECT})")
    parser.add_argument("--training-only", action="store_true",
                        help="Upload only training data")
    parser.add_argument("--logs-only", action="store_true",
                        help="Upload only log files")
    parser.add_argument("--timelines-only", action="store_true",
                        help="Upload only timeline files")
    parser.add_argument("--list", action="store_true",
                        help="List bucket contents instead of uploading")
    parser.add_argument("--sync", action="store_true",
                        help="Only upload new files (skip existing)")
    args = parser.parse_args()

    print(f"🔗 Connecting to GCS...")
    print(f"   Project: {args.project}")
    print(f"   Bucket:  {args.bucket}")
    if args.sync:
        print(f"   Mode:    SYNC (skip existing files)")

    client = get_client(project=args.project)

    if args.list:
        list_bucket(client, args.bucket)
        return

    if args.training_only:
        upload_training_data(client, args.bucket, sync=args.sync)
    elif args.logs_only:
        upload_logs(client, args.bucket, sync=args.sync)
    elif args.timelines_only:
        upload_timelines(client, args.bucket, sync=args.sync)
    else:
        upload_all(client, args.bucket, sync=args.sync)

    print("")
    print("✅ Upload complete!")
    list_bucket(client, args.bucket)


if __name__ == "__main__":
    main()