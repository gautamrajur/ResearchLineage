# batch_run.py
import argparse
import json
import os
import time
from typing import Any, Dict, List, Optional, Set

from pipeline import build_timeline
from data_export import save_timeline_json
from config import VERBOSE
import logging
import traceback
from config import logger
print = logger.info


STATE_FILE_DEFAULT = "run_state.jsonl"


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_seeds(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("seeds.json must be a JSON list")
    # normalize
    seeds: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, str):
            seeds.append({"paperId": item})
        elif isinstance(item, dict):
            # accept paperId or paper_id
            pid = item.get("paperId") or item.get("paper_id")
            if pid:
                seeds.append({**item, "paperId": pid})
    return seeds


def load_done_seed_ids(state_file: str) -> Set[str]:
    """
    Read run_state.jsonl and return seed paperIds that already completed successfully.
    """
    done: Set[str] = set()
    if not os.path.exists(state_file):
        return done

    with open(state_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") == "success":
                pid = rec.get("seed_paper_id")
                if pid:
                    done.add(pid)
    return done


def append_state(state_file: str, record: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    with open(state_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_filename(text: str, max_len: int = 80) -> str:
    if not text:
        return "unknown"
    text = text.strip()
    cleaned = "".join(c if (c.isalnum() or c in " -_") else "" for c in text)
    cleaned = cleaned.strip().replace(" ", "_")
    if not cleaned:
        return "unknown"
    return cleaned[:max_len]


def run_one_seed(seed: Dict[str, Any], depth: int) -> Optional[str]:
    """
    Run build_timeline for a seed and save timeline JSON.

    Returns:
        filepath of saved timeline json, or None if failed.
    """
    seed_id = seed.get("paperId")
    if not seed_id:
        return None

    timeline = build_timeline(seed_id, max_depth=depth)
    if not timeline:
        return None

    # Name file deterministically: include seed paperId + (optional) title
    title = seed.get("title") or (timeline[0].get("target_paper", {}) or {}).get("title") or ""
    filename = f"seed_{safe_filename(seed_id, 16)}_{safe_filename(title, 30)}.json"
    filepath = save_timeline_json(timeline, filename=filename)
    return filepath


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=str, default="inputs/seeds.json")
    ap.add_argument("--depth", type=int, default=3, help="Max depth per seed")
    ap.add_argument("--max-seeds", type=int, default=5, help="How many seeds to run this session")
    ap.add_argument("--state", type=str, default=os.path.join("outputs", "run_state.jsonl"))
    ap.add_argument("--resume", action="store_true", help="Skip seeds already marked success in state file")
    ap.add_argument("--sleep", type=float, default=2.0, help="Seconds to sleep between seeds")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds)
    if not seeds:
        print("❌ No seeds found.")
        return

    done = load_done_seed_ids(args.state) if args.resume else set()

    # build run list
    run_list: List[Dict[str, Any]] = []
    for s in seeds:
        pid = s.get("paperId")
        if not pid:
            continue
        if args.resume and pid in done:
            if VERBOSE:
                print(f"⏭️  Skipping already-done seed: {pid}")
            continue
        run_list.append(s)
        if len(run_list) >= args.max_seeds:
            break

    if not run_list:
        print("✅ Nothing to run (all done or no valid seeds).")
        return

    print(f"\n🚀 Batch run starting")
    print(f"   Seeds file: {args.seeds}")
    print(f"   Depth: {args.depth}")
    print(f"   This session: {len(run_list)} seeds")
    print(f"   State file: {args.state}")
    print("")

    successes = 0
    failures = 0

    for idx, seed in enumerate(run_list, 1):
        seed_id = seed.get("paperId")
        domain = seed.get("domain")
        title = seed.get("title")

        print(f"\n{'='*70}")
        print(f"🌱 Seed {idx}/{len(run_list)}: {seed_id}")
        if title:
            print(f"   Title: {title}")
        if domain:
            print(f"   Domain: {domain}")
        print(f"   Started: {_now_str()}")
        print(f"{'='*70}")

        try:
            filepath = run_one_seed(seed, depth=args.depth)
            if filepath:
                successes += 1
                append_state(args.state, {
                    "timestamp": _now_str(),
                    "seed_paper_id": seed_id,
                    "status": "success",
                    "depth": args.depth,
                    "timeline_path": filepath,
                    "domain": domain,
                    "title": title,
                })
                print(f"✅ Success: saved timeline → {filepath}")
            else:
                failures += 1
                append_state(args.state, {
                    "timestamp": _now_str(),
                    "seed_paper_id": seed_id,
                    "status": "failed",
                    "depth": args.depth,
                    "domain": domain,
                    "title": title,
                    "error": "build_timeline returned empty/None",
                })
                print("❌ Failed: build_timeline returned no results")

        except KeyboardInterrupt:
            append_state(args.state, {
                "timestamp": _now_str(),
                "seed_paper_id": seed_id,
                "status": "interrupted",
                "depth": args.depth,
                "domain": domain,
                "title": title,
            })
            print("\n🛑 Interrupted by user. Exiting.")
            break

        except Exception as e:
            failures += 1
            append_state(args.state, {
                "timestamp": _now_str(),
                "seed_paper_id": seed_id,
                "status": "failed",
                "depth": args.depth,
                "domain": domain,
                "title": title,
                "error": repr(e),
            })
            print(f"❌ Exception: {e!r}")

        time.sleep(max(0.0, args.sleep))

    print(f"\n🏁 Batch run finished at {_now_str()}")
    print(f"   Successes: {successes}")
    print(f"   Failures:  {failures}")
    print(f"   State log: {args.state}")


if __name__ == "__main__":
    main()