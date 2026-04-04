"""
demo_cache_run.py
-----------------
Runs build_tree() twice on the same paper to prove caching works.

Run 1  -> cold cache  -> all API calls  -> saved to cold_run.json
Run 2  -> warm cache  -> all DB reads   -> saved to warm_run.json

Both JSONs are printed and diffed so you can verify they are identical.

Usage:
    cd ResearchLineage
    python demo_cache_run.py
"""

import os
import sys
import json
import time
import logging

sys.path.insert(0, os.path.dirname(__file__))

from tree_view.tree_builder import TreeView, setup_logging
from tree_view.cache import DATABASE_URL

PAPER_ID   = "ARXIV:1706.03762"  # Attention Is All You Need
LOG_FILE   = "tree_builder.log"
COLD_JSON  = "cold_run.json"
WARM_JSON  = "warm_run.json"
MAX_DEPTH  = 3
MAX_CHILD  = 3
WINDOW     = 3


def section(title):
    bar = "-" * 70
    print(f"\n{bar}")
    print(f"  {title}")
    print(f"{bar}\n")


def wipe(path):
    p = os.path.abspath(path)
    if os.path.exists(p):
        os.remove(p)
        print(f"[wipe] Deleted: {p}")
    else:
        print(f"[wipe] Not found (ok): {p}")


def count_nodes(nodes, child_key):
    total = 0
    for n in nodes:
        total += 1 + count_nodes(n.get(child_key, []), child_key)
    return total


def summarise(tree, label):
    if tree is None:
        print(f"  {label}: FAILED")
        return
    t = tree['target']
    n_anc  = count_nodes(tree['ancestors'],   'ancestors')
    n_desc = count_nodes(tree['descendants'], 'children')
    print(f"  {label}")
    print(f"    Target      : {t.get('title','?')[:65]}")
    print(f"    Year        : {t.get('year','?')}")
    print(f"    Citations   : {t.get('citationCount','?')}")
    print(f"    Ancestors   : {n_anc} nodes")
    print(f"    Descendants : {n_desc} nodes")


def save_json(tree, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {os.path.abspath(path)}")


def trees_equal(t1, t2):
    """Deep equality check ignoring key order."""
    return json.dumps(t1, sort_keys=True) == json.dumps(t2, sort_keys=True)


def diff_keys(d1, d2, path=""):
    """Recursively find keys/values that differ between two dicts/lists."""
    diffs = []
    if type(d1) != type(d2):
        diffs.append(f"  {path}: type mismatch {type(d1).__name__} vs {type(d2).__name__}")
        return diffs
    if isinstance(d1, dict):
        all_keys = set(d1) | set(d2)
        for k in sorted(all_keys):
            p = f"{path}.{k}" if path else k
            if k not in d1:
                diffs.append(f"  {p}: missing in cold")
            elif k not in d2:
                diffs.append(f"  {p}: missing in warm")
            else:
                diffs.extend(diff_keys(d1[k], d2[k], p))
    elif isinstance(d1, list):
        if len(d1) != len(d2):
            diffs.append(f"  {path}: list length {len(d1)} vs {len(d2)}")
        for i, (a, b) in enumerate(zip(d1, d2)):
            diffs.extend(diff_keys(a, b, f"{path}[{i}]"))
    else:
        if d1 != d2:
            diffs.append(f"  {path}: {repr(d1)} != {repr(d2)}")
    return diffs


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Wipe log and previous JSON outputs (DB is managed by PostgreSQL now)
    section("SETUP -- wiping log and previous JSON outputs")
    wipe(LOG_FILE)
    wipe(COLD_JSON)
    wipe(WARM_JSON)

    # Setup logging AFTER wiping the log file
    setup_logging(log_file=LOG_FILE, level=logging.DEBUG)
    log = logging.getLogger("tree_builder")
    log.info("demo_cache_run.py  paper=%s  depth=%d  children=%d  window=%d",
             PAPER_ID, MAX_DEPTH, MAX_CHILD, WINDOW)

    print(f"\nPaper    : {PAPER_ID}")
    print(f"DB       : {DATABASE_URL}")
    print(f"Log      : {os.path.abspath(LOG_FILE)}")
    print(f"Settings : max_depth={MAX_DEPTH}  max_children={MAX_CHILD}  window={WINDOW}")

    # -----------------------------------------------------------------------
    # RUN 1 -- cold cache
    # -----------------------------------------------------------------------
    section("RUN 1 -- Cold cache (all API calls)")
    log.info("=" * 60)
    log.info("RUN 1  cold cache")
    log.info("=" * 60)

    tv = TreeView(dsn=DATABASE_URL)
    t1_start = time.perf_counter()
    tree1 = tv.build_tree(PAPER_ID, max_children=MAX_CHILD,
                          max_depth=MAX_DEPTH, window_years=WINDOW)
    elapsed1 = time.perf_counter() - t1_start

    summarise(tree1, "Run 1 result")
    print(f"\n  Wall-clock time: {elapsed1:.1f}s")
    save_json(tree1, COLD_JSON)

    # -----------------------------------------------------------------------
    # RUN 2 -- warm cache
    # -----------------------------------------------------------------------
    section("RUN 2 -- Warm cache (all DB reads, zero API calls)")
    log.info("=" * 60)
    log.info("RUN 2  warm cache")
    log.info("=" * 60)

    t2_start = time.perf_counter()
    tree2 = tv.build_tree(PAPER_ID, max_children=MAX_CHILD,
                          max_depth=MAX_DEPTH, window_years=WINDOW)
    elapsed2 = time.perf_counter() - t2_start

    summarise(tree2, "Run 2 result")
    print(f"\n  Wall-clock time: {elapsed2:.1f}s")
    save_json(tree2, WARM_JSON)

    # -----------------------------------------------------------------------
    # Timing comparison
    # -----------------------------------------------------------------------
    section("TIMING COMPARISON")
    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float('inf')
    print(f"  Run 1 (cold) : {elapsed1:7.2f}s")
    print(f"  Run 2 (cache): {elapsed2:7.2f}s")
    print(f"  Speed-up     : {speedup:.1f}x")

    # -----------------------------------------------------------------------
    # JSON equality check
    # -----------------------------------------------------------------------
    section("JSON EQUALITY CHECK  (cold_run.json  vs  warm_run.json)")

    if tree1 is None or tree2 is None:
        print("  Cannot compare -- one or both runs failed.")
    elif trees_equal(tree1, tree2):
        print("  MATCH -- both trees are byte-for-byte identical.")
        print()
        print("  Cold run JSON (first 60 lines):")
        print("  " + "-" * 60)
        cold_lines = json.dumps(tree1, indent=2, ensure_ascii=False).splitlines()
        for line in cold_lines[:60]:
            print("  " + line)
        if len(cold_lines) > 60:
            print(f"  ... ({len(cold_lines) - 60} more lines, see cold_run.json)")
    else:
        diffs = diff_keys(tree1, tree2)
        print(f"  MISMATCH -- {len(diffs)} differences found:")
        for d in diffs[:30]:
            print(d)
        if len(diffs) > 30:
            print(f"  ... and {len(diffs) - 30} more")
        print()
        print("  Cold JSON (first 40 lines):")
        for line in json.dumps(tree1, indent=2).splitlines()[:40]:
            print("  " + line)
        print()
        print("  Warm JSON (first 40 lines):")
        for line in json.dumps(tree2, indent=2).splitlines()[:40]:
            print("  " + line)

    print()
    print(f"  Full files : {os.path.abspath(COLD_JSON)}")
    print(f"               {os.path.abspath(WARM_JSON)}")
    print(f"  Full log   : {os.path.abspath(LOG_FILE)}")
    print()
