"""Data preparation for Custom Training.

This module handles:
1. Loading raw training data from lineage_pipeline output
2. Truncating examples to fit within token limits
3. Converting to the format expected by the training script
4. Uploading prepared data to GCS

Key Difference from Managed SFT:
- We control truncation (no hard 4096 limit)
- We can do more sophisticated preprocessing
- Format is simpler: {"input": "...", "output": "..."}

Usage:
    # Prepare data from pipeline output
    python -m temporary.ft_data_prep --prepare
    
    # Upload to GCS
    python -m temporary.ft_data_prep --upload
    
    # Full pipeline
    python -m temporary.ft_data_prep --prepare --upload
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Default paths
DEFAULT_INPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "tasks" / "pipeline_output" / "llama_format"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "ft_data"


def load_jsonl(filepath: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file."""
    samples = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def save_jsonl(samples: List[Dict[str, Any]], filepath: Path) -> None:
    """Save samples to JSONL file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    logger.info(f"Saved {len(samples)} samples to {filepath}")


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to approximately max_chars while trying to keep it coherent.
    
    Attempts to truncate at sentence boundaries when possible.
    """
    if len(text) <= max_chars:
        return text
    
    # Find a good break point
    truncated = text[:max_chars]
    
    # Try to break at a sentence boundary
    for sep in ["\n\n", ". ", ".\n", "\n"]:
        last_break = truncated.rfind(sep)
        if last_break > max_chars * 0.7:  # Only if we keep at least 70%
            return truncated[:last_break + len(sep)].strip()
    
    # Fallback: break at word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.9:
        return truncated[:last_space].strip() + "..."
    
    return truncated.strip() + "..."


def extract_key_sections(text: str, max_chars: int) -> str:
    """Extract the most important sections from a long prompt.
    
    For our lineage analysis task, the most important parts are:
    1. The TARGET PAPER section
    2. The first 2-3 CANDIDATE sections
    
    This is more intelligent than simple truncation.
    """
    # If already short enough, return as-is
    if len(text) <= max_chars:
        return text
    
    parts = []
    current_len = 0
    
    # Always include the prompt instructions (first ~2000 chars or until TARGET PAPER)
    target_idx = text.find("TARGET PAPER")
    if target_idx == -1:
        # No structure found, just truncate
        return truncate_text(text, max_chars)
    
    # Include prompt header
    header = text[:target_idx]
    if len(header) > 2000:
        header = truncate_text(header, 2000)
    parts.append(header)
    current_len += len(header)
    
    # Extract TARGET PAPER section
    candidates_idx = text.find("CANDIDATE PREDECESSOR PAPERS")
    if candidates_idx == -1:
        candidates_idx = text.find("CANDIDATE 1")
    
    if candidates_idx > target_idx:
        target_section = text[target_idx:candidates_idx]
        # Limit target section
        max_target = min(4000, max_chars // 2)
        if len(target_section) > max_target:
            target_section = truncate_text(target_section, max_target)
        parts.append(target_section)
        current_len += len(target_section)
    
    # Extract candidate sections (keep first 2-3)
    remaining_budget = max_chars - current_len
    if candidates_idx != -1 and remaining_budget > 500:
        candidates_text = text[candidates_idx:]
        
        # Split by candidate markers
        import re
        candidate_pattern = r"(CANDIDATE \d+.*?)(?=CANDIDATE \d+|$)"
        candidates = re.findall(candidate_pattern, candidates_text, re.DOTALL)
        
        candidate_budget = remaining_budget // min(3, len(candidates)) if candidates else remaining_budget
        
        parts.append("\n" + "=" * 60 + "\nCANDIDATE PREDECESSOR PAPERS\n" + "=" * 60)
        
        for i, cand in enumerate(candidates[:3]):  # Max 3 candidates
            if current_len >= max_chars - 200:
                break
            truncated_cand = truncate_text(cand, candidate_budget)
            parts.append(truncated_cand)
            current_len += len(truncated_cand)
    
    return "\n".join(parts)


def prepare_sample(
    sample: Dict[str, Any],
    max_input_chars: int = 8000,
    max_output_chars: int = 4000,
) -> Optional[Dict[str, str]]:
    """Prepare a single sample for training.
    
    Args:
        sample: Raw sample from pipeline output
        max_input_chars: Maximum characters for input
        max_output_chars: Maximum characters for output
        
    Returns:
        Prepared sample with truncated input/output, or None if invalid
    """
    # Handle both formats: {"input_text", "output_text"} and {"input", "output"}
    input_text = sample.get("input_text") or sample.get("input", "")
    output_text = sample.get("output_text") or sample.get("output", "")
    
    if not input_text or not output_text:
        return None
    
    # Use intelligent extraction for input
    prepared_input = extract_key_sections(input_text, max_input_chars)
    
    # Simple truncation for output (it's structured JSON)
    prepared_output = truncate_text(output_text, max_output_chars)
    
    # Validate output is still valid JSON
    try:
        json.loads(prepared_output.rstrip("..."))
    except json.JSONDecodeError:
        # Try to find the last complete JSON object
        # This is a simplified approach - in production, use proper JSON streaming
        if prepared_output.endswith("..."):
            # Find last complete object
            depth = 0
            last_valid = 0
            for i, c in enumerate(prepared_output):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        last_valid = i + 1
            if last_valid > 0:
                prepared_output = prepared_output[:last_valid]
    
    return {
        "input": prepared_input,
        "output": prepared_output,
    }


def prepare_dataset(
    input_dir: Path,
    output_dir: Path,
    max_input_chars: int = 8000,
    max_output_chars: int = 4000,
    min_samples: int = 10,
) -> Dict[str, int]:
    """Prepare the full dataset for training.
    
    Args:
        input_dir: Directory containing train.jsonl, val.jsonl from pipeline
        output_dir: Directory to write prepared data
        max_input_chars: Maximum input length
        max_output_chars: Maximum output length
        min_samples: Minimum samples required
        
    Returns:
        Statistics about the prepared data
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = {}
    
    for split in ["train", "val", "test"]:
        input_file = input_dir / f"{split}.jsonl"
        
        if not input_file.exists():
            logger.warning(f"Input file not found: {input_file}")
            stats[split] = 0
            continue
        
        samples = load_jsonl(input_file)
        logger.info(f"Loaded {len(samples)} samples from {split}")
        
        prepared = []
        for sample in samples:
            p = prepare_sample(sample, max_input_chars, max_output_chars)
            if p:
                prepared.append(p)
        
        if len(prepared) < min_samples and split == "train":
            logger.error(
                f"Only {len(prepared)} training samples after preparation. "
                f"Need at least {min_samples}. "
                f"Run the lineage pipeline to generate more data."
            )
        
        output_file = output_dir / f"{split}.jsonl"
        save_jsonl(prepared, output_file)
        
        # Log statistics
        input_lens = [len(s["input"]) for s in prepared]
        output_lens = [len(s["output"]) for s in prepared]
        
        logger.info(f"{split}: {len(prepared)} samples")
        if prepared:
            logger.info(f"  Input chars: min={min(input_lens)}, max={max(input_lens)}, avg={sum(input_lens)//len(input_lens)}")
            logger.info(f"  Output chars: min={min(output_lens)}, max={max(output_lens)}, avg={sum(output_lens)//len(output_lens)}")
            logger.info(f"  Approx tokens: ~{sum(input_lens)//4 // len(input_lens)} input, ~{sum(output_lens)//4 // len(output_lens)} output")
        
        stats[split] = len(prepared)
    
    return stats


def upload_to_gcs(local_dir: Path, gcs_prefix: str) -> List[str]:
    """Upload prepared data to GCS using ADC.

    Args:
        local_dir: Local directory containing prepared data
        gcs_prefix: GCS prefix (unused — prefix is read from CustomTrainConfig)

    Returns:
        List of uploaded GCS URIs
    """
    from google.cloud import storage

    from temporary.ft_custom_config import CustomTrainConfig
    cfg = CustomTrainConfig()

    # ADC: no credentials arg needed
    client = storage.Client(project=cfg.project_id)
    bucket = client.bucket(cfg.bucket)
    
    uploaded = []
    
    for filepath in local_dir.glob("*.jsonl"):
        # Construct GCS path
        gcs_path = f"{cfg.ft_prefix}/{filepath.name}" if cfg.ft_prefix else filepath.name
        
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(str(filepath))
        
        gcs_uri = f"gs://{cfg.bucket}/{gcs_path}"
        uploaded.append(gcs_uri)
        logger.info(f"Uploaded: {filepath.name} -> {gcs_uri}")
    
    return uploaded


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare training data for Vertex AI Custom Training"
    )
    
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare data (truncate, format)"
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload prepared data to GCS"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(DEFAULT_INPUT_DIR),
        help="Input directory with raw pipeline output"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for prepared data"
    )
    parser.add_argument(
        "--max-input-chars",
        type=int,
        default=8000,
        help="Maximum input characters"
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=4000,
        help="Maximum output characters"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about existing prepared data"
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    
    if args.stats:
        for split in ["train", "val", "test"]:
            filepath = output_dir / f"{split}.jsonl"
            if filepath.exists():
                samples = load_jsonl(filepath)
                print(f"\n{split}: {len(samples)} samples")
                if samples:
                    input_lens = [len(s.get("input", "")) for s in samples]
                    output_lens = [len(s.get("output", "")) for s in samples]
                    print(f"  Input: {min(input_lens)}-{max(input_lens)} chars")
                    print(f"  Output: {min(output_lens)}-{max(output_lens)} chars")
        return
    
    if args.prepare:
        logger.info(f"Input dir: {input_dir}")
        logger.info(f"Output dir: {output_dir}")
        
        stats = prepare_dataset(
            input_dir=input_dir,
            output_dir=output_dir,
            max_input_chars=args.max_input_chars,
            max_output_chars=args.max_output_chars,
        )
        
        print("\n" + "=" * 50)
        print("Data Preparation Complete")
        print("=" * 50)
        for split, count in stats.items():
            print(f"  {split}: {count} samples")
    
    if args.upload:
        logger.info(f"Uploading from: {output_dir}")
        uploaded = upload_to_gcs(output_dir, "")
        
        print("\n" + "=" * 50)
        print("Upload Complete")
        print("=" * 50)
        for uri in uploaded:
            print(f"  {uri}")
    
    if not args.prepare and not args.upload and not args.stats:
        parser.print_help()


if __name__ == "__main__":
    main()
