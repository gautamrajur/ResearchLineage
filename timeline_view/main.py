"""
main.py - Entry point for ResearchLineage Timeline Pipeline

Usage:
    python main.py                              # Uses default paper (Transformer)
    python main.py 1706.03762                   # arXiv ID
    python main.py https://arxiv.org/abs/1706.03762   # arXiv URL
    python main.py --depth 4 1706.03762         # Custom depth
"""

import sys
import os

from config import MAX_DEPTH, GEMINI_API_KEY
from pipeline import build_timeline, display_timeline
from data_export import save_timeline_json, count_training_examples


def main():
    # --- Parse arguments ---
    paper_id = "1706.03762"  # Default: Attention Is All You Need
    depth = MAX_DEPTH

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--depth" and i + 1 < len(args):
            depth = int(args[i + 1])
            i += 2
        else:
            paper_id = args[i]
            i += 1

    # --- Check API key ---
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("❌ Please set your Gemini API key in config.py or as environment variable:")
        print("   export GEMINI_API_KEY='your_key_here'")
        sys.exit(1)

    # --- Run pipeline ---
    print(f"\n🔬 ResearchLineage Timeline Pipeline")
    print(f"   Paper: {paper_id}")
    print(f"   Max depth: {depth}")
    print(f"   Training examples so far: {count_training_examples()}")
    print()

    timeline = build_timeline(paper_id, max_depth=depth)

    if not timeline:
        print("\n❌ Pipeline produced no results.")
        sys.exit(1)

    # --- Display ---
    display_timeline(timeline)

    # --- Save ---
    filepath = save_timeline_json(timeline)

    # --- Summary ---
    print(f"\n📊 Summary:")
    print(f"   Papers in lineage: {len(timeline)}")
    print(f"   Timeline saved: {filepath}")
    print(f"   Training examples total: {count_training_examples()}")


if __name__ == "__main__":
    main()