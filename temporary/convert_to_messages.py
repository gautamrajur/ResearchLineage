"""Convert input_text/output_text JSONL to messages format for Vertex AI Managed SFT.

Converts from:
    {"input_text": "...", "output_text": "..."}

To:
    {"messages": [{"role": "user", "content": "..."}, {"role": "model", "content": "..."}]}

Note: Vertex AI uses "model" instead of "assistant" for the response role.

Usage:
    python convert_to_messages.py input.jsonl output.jsonl
    python convert_to_messages.py  # Uses default paths
"""
import json
import argparse
from pathlib import Path


def convert_line(line: str) -> str:
    """Convert a single JSONL line from input_text/output_text to messages format."""
    data = json.loads(line.strip())
    
    input_text = data.get("input_text", "")
    output_text = data.get("output_text", "")
    
    # Convert to messages format
    # Vertex AI uses "model" not "assistant"
    converted = {
        "messages": [
            {"role": "user", "content": input_text},
            {"role": "model", "content": output_text}
        ]
    }
    
    return json.dumps(converted, ensure_ascii=False)


def _resolve_path(path: str) -> Path:
    """Resolve path; if relative, interpret relative to script dir (temporary/) so ft_data/ works."""
    p = Path(path)
    if not p.is_absolute():
        script_dir = Path(__file__).resolve().parent
        p = (script_dir / path).resolve()
    return p


def convert_file(input_path: str, output_path: str, max_examples: int = None):
    """Convert entire JSONL file."""
    input_path = _resolve_path(input_path)
    output_path = _resolve_path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Converting: {input_path} -> {output_path}")

    converted_count = 0
    skipped_count = 0
    
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for i, line in enumerate(infile):
            if max_examples and i >= max_examples:
                print(f"Stopped at {max_examples} examples (--max flag)")
                break
                
            line = line.strip()
            if not line:
                continue
            
            try:
                converted = convert_line(line)
                outfile.write(converted + '\n')
                converted_count += 1
                
                if converted_count % 100 == 0:
                    print(f"  Converted {converted_count} examples...")
                    
            except json.JSONDecodeError as e:
                print(f"  Skipping line {i+1}: JSON decode error - {e}")
                skipped_count += 1
            except KeyError as e:
                print(f"  Skipping line {i+1}: Missing key - {e}")
                skipped_count += 1
    
    print(f"\nDone!")
    print(f"  Converted: {converted_count} examples")
    print(f"  Skipped: {skipped_count} examples")
    print(f"  Output: {output_path}")
    
    # Show a sample of the converted data
    print(f"\nSample of converted data (first 500 chars):")
    with open(output_path, 'r', encoding='utf-8') as f:
        first_line = f.readline()
        print(first_line[:500] + "..." if len(first_line) > 500 else first_line)


def main():
    parser = argparse.ArgumentParser(
        description="Convert input_text/output_text JSONL to messages format"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="ft_data/train.jsonl",
        help="Input JSONL file path"
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="ft_data/train_messages.jsonl",
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Maximum number of examples to convert"
    )
    
    args = parser.parse_args()
    convert_file(args.input, args.output, args.max)


if __name__ == "__main__":
    main()
