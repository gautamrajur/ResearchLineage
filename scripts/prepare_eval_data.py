# scripts/prepare_eval_data.py
"""
Converts raw training/validation JSONL files (input_text / output_text format)
into the pipeline-ready format (input_text / ground_truth) and uploads to GCS.

Usage:
    poetry run python scripts/prepare_eval_data.py \
        --input  E:/ResearchLineage/Fine-Tuning/test.jsonl \
        --bucket gs://research-lineage-eval/eval/inputs/eval_data.jsonl \
        --project research-lineage-eval

Or to just convert locally without uploading:
    poetry run python scripts/prepare_eval_data.py \
        --input  E:/ResearchLineage/Fine-Tuning/test.jsonl \
        --output E:/ResearchLineage/Fine-Tuning/eval_data_prepared.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def parse_output_text(output_text: str) -> dict:
    """
    The output_text field is either:
      - A raw JSON string
      - A JSON string wrapped in ```json ... ``` fences
    Also handles trailing commas before } or ] — a common Gemini generation artifact.
    Returns the parsed dict, or raises ValueError with a clear message.
    """
    cleaned = output_text.strip()

    # strip ```json ... ``` fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    # find outermost { ... } block
    brace = re.search(r"\{[\s\S]+\}", cleaned)
    if brace:
        cleaned = brace.group(0)

    # remove trailing commas before } or ] (Gemini artifact)
    # e.g. "last item",\n    } -> "last item"\n    }
    cleaned = re.sub(r",\s*(\}|\])", r"\1", cleaned)

    return json.loads(cleaned)


def convert_record(raw: dict, index: int) -> dict | None:
    """
    Convert one raw record from {input_text, output_text} format
    to {sample_id, input_text, ground_truth} format.
    Returns None and prints a warning if the record is unparseable.
    """
    input_text = raw.get("input_text", "")
    output_text = raw.get("output_text", "")

    if not input_text:
        print(f"[WARN] record {index}: empty input_text — skipping")
        return None

    if not output_text:
        print(f"[WARN] record {index}: empty output_text — skipping")
        return None

    try:
        ground_truth = parse_output_text(output_text)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[WARN] record {index}: could not parse output_text — {exc} — skipping")
        return None

    # generate a stable sample_id from index
    sample_id = f"sample_{index:05d}"

    return {
        "sample_id": sample_id,
        "input_text": input_text,
        "ground_truth": ground_truth,
    }


def convert_file(input_path: Path) -> list[dict]:
    """Read and convert all records from the input JSONL file."""
    records = []
    skipped = 0

    with open(input_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[WARN] line {i}: malformed JSON — {exc} — skipping")
                skipped += 1
                continue

            converted = convert_record(raw, i)
            if converted is not None:
                records.append(converted)
            else:
                skipped += 1

    print(f"\nConverted {len(records)} records, skipped {skipped}")
    return records


def save_local(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Saved to {output_path}")


def upload_to_gcs(records: list[dict], gcs_uri: str, project_id: str) -> None:
    from google.cloud import storage

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")

    without_scheme = gcs_uri[5:]
    bucket_name, _, blob_name = without_scheme.partition("/")

    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"

    blob.upload_from_string(content, content_type="application/json")
    print(f"Uploaded {len(records)} records to {gcs_uri}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert raw JSONL eval data and optionally upload to GCS."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to raw JSONL file (input_text / output_text format).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Local output path for converted JSONL. "
        "If omitted, a _prepared.jsonl file is written next to the input.",
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help="GCS URI to upload to, e.g. gs://my-bucket/eval/inputs/eval_data.jsonl. "
        "If provided, also uploads after local conversion.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="GCP project ID. Required if --bucket is set.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    # determine local output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(input_path.stem + "_prepared.jsonl")

    print(f"Reading from : {input_path}")
    records = convert_file(input_path)

    if not records:
        print("[ERROR] No valid records found. Aborting.")
        sys.exit(1)

    save_local(records, output_path)

    if args.bucket:
        if not args.project:
            print("[ERROR] --project is required when --bucket is set.")
            sys.exit(1)
        upload_to_gcs(records, args.bucket, args.project)


if __name__ == "__main__":
    main()
