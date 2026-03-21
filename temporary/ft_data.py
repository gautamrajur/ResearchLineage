"""Training data utilities for Vertex AI Managed SFT.

This module provides utilities for preparing and validating training data
for Vertex AI Managed SFT fine-tuning.

Data Format Requirements:
The training data should be in JSONL format with one of these structures:

1. Prompt-completion format:
   {"prompt": "...", "completion": "..."}

2. Turn-based chat format (recommended):
   {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Usage:
    python -m temporary.ft_data --validate ./data/train.jsonl
    python -m temporary.ft_data --upload ./data/train.jsonl
    python -m temporary.ft_data --check
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from google.cloud import storage
from google.oauth2 import service_account

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_gcs_client():
    """Get GCS client with service account credentials."""
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    credentials = service_account.Credentials.from_service_account_file(
        cfg.service_account_key,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    
    return storage.Client(credentials=credentials, project=cfg.project_id)


def validate_jsonl(file_path: str) -> Dict[str, Any]:
    """Validate JSONL file format for Vertex AI Managed SFT.
    
    Args:
        file_path: Path to JSONL file
        
    Returns:
        Validation report
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    report = {
        "file": str(file_path),
        "valid": True,
        "total_lines": 0,
        "format": None,
        "errors": [],
        "warnings": [],
    }
    
    format_counts = {
        "messages": 0,
        "prompt_completion": 0,
        "unknown": 0,
    }
    
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            report["total_lines"] += 1
            
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                report["errors"].append(f"Line {line_num}: Invalid JSON - {e}")
                report["valid"] = False
                continue
            
            # Detect and validate format
            if "messages" in data:
                format_counts["messages"] += 1
                # Validate messages structure
                if not isinstance(data["messages"], list):
                    report["errors"].append(f"Line {line_num}: 'messages' must be a list")
                    report["valid"] = False
                elif len(data["messages"]) < 2:
                    report["warnings"].append(f"Line {line_num}: messages should have at least 2 turns")
            elif "prompt" in data and "completion" in data:
                format_counts["prompt_completion"] += 1
            else:
                format_counts["unknown"] += 1
                report["warnings"].append(f"Line {line_num}: Unrecognized format")
    
    # Determine primary format
    if format_counts["messages"] > 0:
        report["format"] = "messages (chat)"
    elif format_counts["prompt_completion"] > 0:
        report["format"] = "prompt-completion"
    
    report["format_counts"] = format_counts
    
    return report


def upload_to_gcs(local_path: str, gcs_path: str = None) -> str:
    """Upload training data to GCS.
    
    Args:
        local_path: Path to local JSONL file
        gcs_path: Optional custom GCS path
        
    Returns:
        GCS URI of uploaded file
    """
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(f"File not found: {local_path}")
    
    client = get_gcs_client()
    bucket = client.bucket(cfg.bucket)
    
    # Determine blob name
    if gcs_path:
        blob_name = gcs_path.replace(f"gs://{cfg.bucket}/", "")
    else:
        blob_name = f"{cfg.ft_prefix}/train.jsonl" if cfg.ft_prefix else "train.jsonl"
    
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    
    gcs_uri = f"gs://{cfg.bucket}/{blob_name}"
    logger.info(f"Uploaded {local_path} to {gcs_uri}")
    
    return gcs_uri


def download_from_gcs(gcs_uri: str, local_path: str = None) -> str:
    """Download file from GCS.
    
    Args:
        gcs_uri: GCS URI
        local_path: Optional local path
        
    Returns:
        Local file path
    """
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    
    parts = gcs_uri[5:].split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    if local_path is None:
        local_path = f"/tmp/{Path(blob_name).name}"
    
    blob.download_to_filename(local_path)
    logger.info(f"Downloaded {gcs_uri} to {local_path}")
    
    return local_path


def check_training_data_exists() -> bool:
    """Check if training data exists in GCS.
    
    Returns:
        True if train.jsonl exists
    """
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    client = get_gcs_client()
    bucket = client.bucket(cfg.bucket)
    
    blob_name = f"{cfg.ft_prefix}/train.jsonl" if cfg.ft_prefix else "train.jsonl"
    blob = bucket.blob(blob_name)
    
    exists = blob.exists()
    
    print(f"\nTraining Data Check:")
    print(f"  URI: {cfg.train_uri()}")
    print(f"  Status: {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
    
    if exists:
        blob.reload()
        print(f"  Size: {blob.size / 1024:.2f} KB")
        print(f"  Updated: {blob.updated}")
    
    return exists


def list_gcs_files(prefix: str = None) -> List[str]:
    """List files in GCS bucket.
    
    Args:
        prefix: Optional prefix to filter
        
    Returns:
        List of file URIs
    """
    from temporary.ft_config import FineTuneConfig
    cfg = FineTuneConfig()
    
    client = get_gcs_client()
    bucket = client.bucket(cfg.bucket)
    
    search_prefix = prefix or cfg.ft_prefix
    blobs = bucket.list_blobs(prefix=search_prefix)
    
    return [f"gs://{cfg.bucket}/{blob.name}" for blob in blobs]


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Training data utilities for Vertex AI"
    )
    
    parser.add_argument("--validate", type=str, help="Validate a JSONL file")
    parser.add_argument("--upload", type=str, help="Upload file to GCS")
    parser.add_argument("--download", type=str, help="Download file from GCS")
    parser.add_argument("--check", action="store_true", help="Check if training data exists")
    parser.add_argument("--list", action="store_true", help="List files in GCS")
    
    args = parser.parse_args()
    
    if args.validate:
        report = validate_jsonl(args.validate)
        print("\n" + "=" * 50)
        print("Validation Report")
        print("=" * 50)
        print(f"File: {report['file']}")
        print(f"Valid: {'✅' if report['valid'] else '❌'}")
        print(f"Total lines: {report['total_lines']}")
        print(f"Format: {report['format']}")
        if report['errors']:
            print(f"\nErrors ({len(report['errors'])}):")
            for err in report['errors'][:5]:
                print(f"  - {err}")
        if report['warnings']:
            print(f"\nWarnings ({len(report['warnings'])}):")
            for warn in report['warnings'][:5]:
                print(f"  - {warn}")
    
    elif args.upload:
        upload_to_gcs(args.upload)
    
    elif args.download:
        download_from_gcs(args.download)
    
    elif args.check:
        check_training_data_exists()
    
    elif args.list:
        files = list_gcs_files()
        print("\nFiles in GCS:")
        for f in files:
            print(f"  {f}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
