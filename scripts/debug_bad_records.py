# scripts/debug_bad_records.py
"""
Inspects bad records in the raw JSONL file to identify the JSON issue.
Run with: poetry run python scripts/debug_bad_records.py
"""
import json
import re

FILEPATH = r"E:\ResearchLineage\Fine-Tuning\test.jsonl"
BAD_INDICES = [2, 5, 6, 13, 15]  # first few bad records from the warnings

with open(FILEPATH, encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")

for idx in BAD_INDICES:
    print(f"\n{'='*60}")
    print(f"RECORD {idx}")
    print(f"{'='*60}")

    try:
        row = json.loads(lines[idx])
    except json.JSONDecodeError as e:
        print(f"Outer JSONL parse error: {e}")
        print(f"Line preview: {lines[idx][:200]}")
        continue

    output_text = row.get("output_text", "")
    print(f"output_text length: {len(output_text)}")

    # try to find the error location
    try:
        # strip fences
        cleaned = output_text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", cleaned)
        if fence:
            cleaned = fence.group(1).strip()
            print("(had code fences, stripped)")
        brace = re.search(r"\{[\s\S]+\}", cleaned)
        if brace:
            cleaned = brace.group(0)
        json.loads(cleaned)
        print("Parses fine after cleaning — no issue found")
    except json.JSONDecodeError as e:
        print(f"JSON error: {e}")
        # print 200 chars around the error position
        pos = e.pos
        start = max(0, pos - 100)
        end = min(len(cleaned), pos + 100)
        print(f"Context around position {pos}:")
        print(repr(cleaned[start:end]))
        print(
            f"\nCharacter at error position: {repr(cleaned[pos]) if pos < len(cleaned) else 'EOF'}"
        )
