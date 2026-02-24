"""
Full Pipeline: Split + Convert for ResearchLineage Training Data
================================================================
Run this single file to:
  1. Split your JSONL into train/val/test (cluster-level stratified)
  2. Convert splits to Llama chat format + metadata sidecar files

Outputs:
  ./lineage_splits/           — split JSONL files (original format)
  ./lineage_llama_format/     — Llama training pairs + metadata for slicing
"""

import json
import re
import pandas as pd
import numpy as np
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ══════════════════════════════════════════════
# PART 1: CLUSTER-LEVEL STRATIFIED SPLITTER
# ══════════════════════════════════════════════

def load_jsonl(filepath: str) -> list[dict]:
    samples = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    print(f"Loaded {len(samples)} samples from {filepath}")
    return samples


def extract_candidate_ids(sample: dict) -> set[str]:
    input_text = sample.get("input", "")
    pattern = r"CANDIDATE \d+ \(Paper ID: ([a-f0-9]+)\)"
    return set(re.findall(pattern, input_text))


def extract_metadata(samples: list[dict]) -> pd.DataFrame:
    rows = []
    for i, sample in enumerate(samples):
        meta = sample.get("metadata", {}) or {}
        level = sample.get("level_info", {}) or {}
        target = level.get("target_paper", {}) or {}
        predecessor = level.get("predecessor_paper", None)

        is_terminal = predecessor is None
        if is_terminal:
            predecessor = {}

        selected_id = meta.get("predecessor_paper_id")
        if not selected_id:
            output = sample.get("output", "")
            if isinstance(output, str):
                try:
                    parsed = json.loads(output)
                    selected_id = parsed.get("selected_predecessor_id")
                except (json.JSONDecodeError, TypeError):
                    pass

        lineage_chain = level.get("lineage_chain", [])
        seed_domain = target.get("field_of_study")
        candidate_ids = extract_candidate_ids(sample)

        row = {
            "sample_index": i,
            "is_terminal": is_terminal,
            "seed_paper_id": meta.get("target_paper_id", target.get("paper_id")),
            "seed_title": meta.get("target_title", target.get("title")),
            "seed_paper_year": target.get("year"),
            "seed_citation_count": target.get("citation_count", 0),
            "seed_field_of_study": seed_domain,
            "predecessor_paper_id": selected_id or predecessor.get("paper_id"),
            "predecessor_paper_year": predecessor.get("year"),
            "predecessor_citation_count": predecessor.get("citation_count", 0),
            "predecessor_field_of_study": seed_domain,
            "depth": meta.get("depth", 0),
            "candidate_list_size": meta.get("candidates_considered", 0),
            "model_used": meta.get("model", "unknown"),
            "source_type": meta.get("target_source_type", "unknown"),
            "lineage_chain": json.dumps(lineage_chain),
            "candidate_ids": json.dumps(list(candidate_ids)),
        }

        if not is_terminal and row["seed_paper_year"] and row["predecessor_paper_year"]:
            row["temporal_gap"] = row["seed_paper_year"] - row["predecessor_paper_year"]
        else:
            row["temporal_gap"] = None

        rows.append(row)

    df = pd.DataFrame(rows)

    # Filter to core domains
    allowed_fields = {"Computer Science", "Mathematics", "Physics"}
    before = len(df)
    df = df[df["seed_field_of_study"].isin(allowed_fields)].reset_index(drop=True)
    removed = before - len(df)
    if removed > 0:
        print(f"  Removed {removed} samples outside core domains")

    df["seed_citation_count"] = df["seed_citation_count"].fillna(0).astype(int)
    df["predecessor_citation_count"] = df["predecessor_citation_count"].fillna(0).astype(int)

    n_terminal = df["is_terminal"].sum()
    print(f"Extracted metadata for {len(df)} samples")
    print(f"  Terminal: {n_terminal} ({n_terminal/len(df):.1%})")
    print(f"  Years: {df['seed_paper_year'].min():.0f} – {df['seed_paper_year'].max():.0f}")
    print(f"  Fields: {df['seed_field_of_study'].nunique()}")
    print(f"  Depths: {df['depth'].min()} – {df['depth'].max()}")

    return df


def compute_lineage_clusters(df: pd.DataFrame) -> pd.DataFrame:
    chains = []
    for _, row in df.iterrows():
        chain = json.loads(row["lineage_chain"])
        chains.append(set(chain) if chain else set())

    parent = list(range(len(df)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    paper_to_samples = defaultdict(list)
    for idx, chain in enumerate(chains):
        for pid in chain:
            paper_to_samples[pid].append(idx)

    for pid, idxs in paper_to_samples.items():
        for j in range(1, len(idxs)):
            union(idxs[0], idxs[j])

    cluster_map = {}
    counter = 0
    cluster_ids = []
    for idx in range(len(df)):
        root = find(idx)
        if root not in cluster_map:
            cluster_map[root] = counter
            counter += 1
        cluster_ids.append(cluster_map[root])

    df = df.copy()
    df["lineage_cluster_id"] = cluster_ids

    n = df["lineage_cluster_id"].nunique()
    print(f"\n  Lineage clusters: {n}")

    return df


def assign_popularity_tier(df: pd.DataFrame, col: str = "seed_citation_count") -> pd.DataFrame:
    df = df.copy()
    values = df[col].dropna()
    if len(values) == 0:
        df["popularity_tier"] = "unknown"
        return df

    p20, p40, p60, p80 = [values.quantile(q) for q in [0.2, 0.4, 0.6, 0.8]]

    bins = [-1, p20, p40, p60, p80, float("inf")]
    labels = ["low", "medium", "high", "very_high", "landmark"]

    unique_bins = [bins[0]]
    unique_labels = []
    for i in range(1, len(bins)):
        if bins[i] > unique_bins[-1]:
            unique_bins.append(bins[i])
            unique_labels.append(labels[i - 1])

    if len(unique_bins) < 2:
        df["popularity_tier"] = "medium"
        return df

    df["popularity_tier"] = pd.cut(df[col], bins=unique_bins, labels=unique_labels, include_lowest=True)

    print(f"  Popularity tiers: low≤{p20:.0f}, med≤{p40:.0f}, high≤{p60:.0f}, vhigh≤{p80:.0f}, landmark>{p80:.0f}")
    return df


def build_cluster_profiles(df: pd.DataFrame) -> pd.DataFrame:
    profiles = []
    for cid, group in df.groupby("lineage_cluster_id"):
        max_year = group["seed_paper_year"].max()
        field = group["seed_field_of_study"].mode().iloc[0]
        tier = group["popularity_tier"].mode().iloc[0]
        size = len(group)
        median_citations = group["seed_citation_count"].median()

        profiles.append({
            "lineage_cluster_id": cid,
            "cluster_size": size,
            "cluster_max_year": max_year,
            "cluster_field": field,
            "cluster_tier": tier,
            "cluster_median_citations": median_citations,
        })

    return pd.DataFrame(profiles)


def stratified_cluster_split(
    cluster_profiles: pd.DataFrame,
    train_frac: float = 0.60,
    val_frac: float = 0.20,
    test_frac: float = 0.20,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    cp = cluster_profiles.copy()
    cp["strat_key"] = cp["cluster_field"] + "_" + cp["cluster_tier"].astype(str)

    assignments = {}

    for key, stratum in cp.groupby("strat_key"):
        stratum = stratum.sort_values("cluster_max_year").reset_index(drop=True)
        n = len(stratum)

        if n == 1:
            for cid in stratum["lineage_cluster_id"]:
                assignments[cid] = "train"
            continue

        if n == 2:
            cids = stratum["lineage_cluster_id"].tolist()
            assignments[cids[0]] = "train"
            assignments[cids[1]] = "test"
            continue

        n_train = max(1, round(n * train_frac))
        n_val = max(1, round(n * val_frac))
        n_test = n - n_train - n_val

        if n_test <= 0:
            n_test = 1
            n_train = n - n_val - n_test

        indices = list(range(n))
        third = n // 3
        for start in range(0, n, max(third, 1)):
            end = min(start + max(third, 1), n)
            block = indices[start:end]
            rng.shuffle(block)
            indices[start:end] = block

        cids = stratum.iloc[indices]["lineage_cluster_id"].tolist()

        for i, cid in enumerate(cids):
            if i < n_train:
                assignments[cid] = "train"
            elif i < n_train + n_val:
                assignments[cid] = "val"
            else:
                assignments[cid] = "test"

    cp["split"] = cp["lineage_cluster_id"].map(assignments)
    return cp


def print_report(splits: dict[str, pd.DataFrame], df_all: pd.DataFrame):
    total = len(df_all)

    print("\n" + "=" * 60)
    print("GLOBAL DATASET DISTRIBUTION")
    print("=" * 60)

    print(f"\n  Total samples: {total}")
    print(f"  Year range: {df_all['seed_paper_year'].min():.0f} – {df_all['seed_paper_year'].max():.0f}")
    print(f"  Lineage clusters: {df_all['lineage_cluster_id'].nunique()}")
    n_term = df_all["is_terminal"].sum()
    print(f"  Terminal samples: {n_term} ({n_term/total:.1%})")

    print(f"\n  Popularity Tiers:")
    for tier, count in df_all["popularity_tier"].value_counts().items():
        print(f"    {tier:12s}: {count:3d} ({count/total:.1%})")

    print(f"\n  Fields:")
    for field, count in df_all["seed_field_of_study"].value_counts().items():
        print(f"    {field:20s}: {count:3d} ({count/total:.1%})")

    print(f"\n  Depth:")
    for depth, count in df_all["depth"].value_counts().sort_index().items():
        print(f"    depth {depth}: {count:3d} ({count/total:.1%})")

    print(f"\n  Citations:")
    print(f"    mean:   {df_all['seed_citation_count'].mean():>10,.0f}")
    print(f"    median: {df_all['seed_citation_count'].median():>10,.0f}")
    print(f"    std:    {df_all['seed_citation_count'].std():>10,.0f}")

    gaps = df_all["temporal_gap"].dropna()
    if len(gaps) > 0:
        print(f"\n  Temporal Gap:")
        print(f"    mean:   {gaps.mean():>6.1f} years")
        print(f"    median: {gaps.median():>6.1f} years")
        print(f"    std:    {gaps.std():>6.1f} years")

    print(f"\n  Candidate List Size:")
    print(f"    mean:   {df_all['candidate_list_size'].mean():>5.1f}")
    print(f"    median: {df_all['candidate_list_size'].median():>5.1f}")

    print("\n" + "=" * 60)
    print("SPLIT SUMMARY")
    print("=" * 60)
    for name in ["train", "val", "test"]:
        n = len(splits[name])
        print(f"  {name:6s}: {n:4d} samples ({n/total:.1%})")

    print("\n" + "=" * 60)
    print("PER-SPLIT DISTRIBUTIONS")
    print("=" * 60)

    for name in ["train", "val", "test"]:
        sdf = splits[name]
        n = len(sdf)
        if n == 0:
            print(f"\n── {name.upper()} — EMPTY ──")
            continue

        print(f"\n── {name.upper()} ({n} samples) ──")
        print(f"  Years: {sdf['seed_paper_year'].min():.0f} – {sdf['seed_paper_year'].max():.0f}")

        print(f"  Popularity:")
        for tier, count in sdf["popularity_tier"].value_counts().items():
            print(f"    {tier:12s}: {count:3d} ({count/n:.1%})")

        print(f"  Fields:")
        for field, count in sdf["seed_field_of_study"].value_counts().items():
            print(f"    {field:20s}: {count:3d} ({count/n:.1%})")

        print(f"  Depth:")
        for depth, count in sdf["depth"].value_counts().sort_index().items():
            print(f"    depth {depth}: {count:3d} ({count/n:.1%})")

        n_term = sdf["is_terminal"].sum()
        print(f"  Terminal: {n_term} ({n_term/n:.1%})")
        print(f"  Citations: mean={sdf['seed_citation_count'].mean():,.0f}  median={sdf['seed_citation_count'].median():,.0f}")

        gaps = sdf["temporal_gap"].dropna()
        if len(gaps) > 0:
            print(f"  Temporal gap: mean={gaps.mean():.1f}y  median={gaps.median():.1f}y")

        print(f"  Candidate list: mean={sdf['candidate_list_size'].mean():.1f}  median={sdf['candidate_list_size'].median():.1f}")
        print(f"  Clusters: {sdf['lineage_cluster_id'].nunique()}")

    # Cross-split comparison
    print("\n" + "=" * 60)
    print("CROSS-SPLIT COMPARISON")
    print("=" * 60)

    split_names = [n for n in ["train", "val", "test"] if len(splits[n]) > 0]

    for dim_name, dim_col in [("Popularity", "popularity_tier"), ("Field", "seed_field_of_study"), ("Depth", "depth")]:
        print(f"\n  {dim_name} Distribution (%):")
        all_vals = sorted(pd.concat(splits.values())[dim_col].dropna().unique(), key=str)
        header = f"    {'':20s}" + "".join(f"{n:>10s}" for n in split_names) + f"{'overall':>10s}"
        print(header)
        for val in all_vals:
            row = f"    {str(val):20s}"
            for name in split_names:
                sdf = splits[name]
                n = len(sdf)
                count = (sdf[dim_col] == val).sum()
                row += f"{count/n*100:>9.1f}%"
            overall_count = (df_all[dim_col] == val).sum()
            row += f"{overall_count/total*100:>9.1f}%"
            print(row)

    # Integrity checks
    print("\n" + "=" * 60)
    print("INTEGRITY CHECKS")
    print("=" * 60)

    all_data = pd.concat([sdf.assign(_split=name) for name, sdf in splits.items()])
    leaked = 0
    for cid, group in all_data.groupby("lineage_cluster_id"):
        if group["_split"].nunique() > 1:
            leaked += 1

    if leaked == 0:
        print("  ✓ Lineage leakage: PASSED")
    else:
        print(f"  ✗ Lineage leakage: FAILED ({leaked} clusters span splits)")

    print("  Paper ID overlap:")
    for i, a in enumerate(split_names):
        for b in split_names[i+1:]:
            ids_a = set()
            for _, row in splits[a].iterrows():
                ids_a.update(json.loads(row["lineage_chain"]))
            ids_b = set()
            for _, row in splits[b].iterrows():
                ids_b.update(json.loads(row["lineage_chain"]))
            overlap = ids_a & ids_b
            status = "✓" if not overlap else "✗"
            print(f"    {status} {a} ↔ {b}: {len(overlap)} shared paper IDs")

    print(f"\n  Sample accounting:")
    for name in split_names:
        print(f"    {name}: {len(splits[name])}")
    print(f"    total: {sum(len(splits[n]) for n in split_names)} / {total}")

def print_all_papers_distribution(splits, samples):
    """Report domain distribution of ALL papers (target + predecessor + candidates) per split."""
    
    print("\n" + "=" * 60)
    print("ALL PAPERS DOMAIN DISTRIBUTION")
    print("=" * 60)
    
    for name in ["train", "val", "test"]:
        sdf = splits[name]
        indices = sdf["sample_index"].tolist()
        
        # Collect all unique paper IDs and their domains from this split
        paper_domains = {}
        for idx in indices:
            sample = samples[idx]
            li = sample.get("level_info", {})
            
            # Target paper
            tp = li.get("target_paper", {})
            if tp.get("paper_id"):
                paper_domains[tp["paper_id"]] = tp.get("field_of_study") or "Unknown"
            
            # Predecessor
            pp = li.get("predecessor_paper") or {}
            if pp.get("paper_id"):
                paper_domains[pp["paper_id"]] = pp.get("field_of_study") or "Unknown"
            
            # Candidates
            for c in li.get("candidates_passed_to_llm", []):
                if c.get("paper_id"):
                    paper_domains[c["paper_id"]] = c.get("field_of_study") or "Unknown"
        
        # Count domains
        from collections import Counter
        domain_counts = Counter(paper_domains.values())
        total = len(paper_domains)
        
        print(f"\n── {name.upper()} ({total} unique papers) ──")
        for domain, count in domain_counts.most_common():
            pct = count / total * 100
            print(f"    {domain:25s}: {count:4d} ({pct:5.1f}%)")


def export_splits(splits, samples, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, sdf in splits.items():
        fp = out / f"{name}.jsonl"
        indices = sdf["sample_index"].tolist()
        with open(fp, "w", encoding="utf-8") as f:
            for idx in indices:
                f.write(json.dumps(samples[idx], ensure_ascii=False) + "\n")
        print(f"  {name}: {len(indices)} samples → {fp}")


def split_dataset(
    filepath: str,
    train_frac: float = 0.60,
    val_frac: float = 0.20,
    test_frac: float = 0.20,
    export_dir: Optional[str] = None,
    seed: int = 42,
):
    samples = load_jsonl(filepath)
    df = extract_metadata(samples)
    df = compute_lineage_clusters(df)
    df = assign_popularity_tier(df)

    profiles = build_cluster_profiles(df)
    print(f"  Built profiles for {len(profiles)} clusters")

    assigned = stratified_cluster_split(profiles, train_frac, val_frac, test_frac, seed)

    cluster_to_split = assigned.set_index("lineage_cluster_id")["split"].to_dict()
    df["split"] = df["lineage_cluster_id"].map(cluster_to_split)

    splits = {
        name: df[df["split"] == name].copy()
        for name in ["train", "val", "test"]
    }

    print_report(splits, df)
    print_all_papers_distribution(splits, samples)

    if export_dir:
        print(f"\nExporting splits:")
        export_splits(splits, samples, export_dir)

    return splits, df, samples


# ══════════════════════════════════════════════
# PART 2: LLAMA FORMAT CONVERTER
# ══════════════════════════════════════════════

def convert_sample(sample: dict) -> dict:
    """Convert a single sample to Llama chat format."""
    user_message = sample.get("input", "")
    assistant_message = sample.get("output", "")
    return {
        "input_text": user_message,
        "output_text": assistant_message,
    }


def convert_file(input_path: str, output_dir: str, split_name: str) -> None:
    """Convert a split JSONL to Llama format + metadata sidecar."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    training_path = out / f"{split_name}.jsonl"
    metadata_path = out / f"{split_name}_metadata.jsonl"

    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    n_converted = 0
    n_skipped = 0

    with open(training_path, "w", encoding="utf-8") as tf, \
         open(metadata_path, "w", encoding="utf-8") as mf:

        for i, sample in enumerate(samples):
            converted = convert_sample(sample)

            if not converted["input_text"] or not converted["output_text"]:
                n_skipped += 1
                continue

            tf.write(json.dumps(converted, ensure_ascii=False) + "\n")

            meta = sample.get("metadata", {}) or {}
            level = sample.get("level_info", {}) or {}
            target = level.get("target_paper", {}) or {}
            predecessor = level.get("predecessor_paper", None) or {}

            metadata_entry = {
                "sample_index": n_converted,
                "original_index": i,
                "seed_paper_id": meta.get("target_paper_id", target.get("paper_id")),
                "seed_paper_year": target.get("year"),
                "seed_citation_count": target.get("citation_count"),
                "seed_field_of_study": target.get("field_of_study"),
                "predecessor_paper_id": meta.get("predecessor_paper_id", predecessor.get("paper_id")),
                "predecessor_paper_year": predecessor.get("year"),
                "depth": meta.get("depth", 0),
                "candidate_list_size": meta.get("candidates_considered", 0),
                "source_type": meta.get("target_source_type"),
                "model_used": meta.get("model"),
                "lineage_chain": level.get("lineage_chain", []),
                "is_terminal": level.get("predecessor_paper") is None,
            }
            mf.write(json.dumps(metadata_entry, ensure_ascii=False) + "\n")

            n_converted += 1

    print(f"  {split_name}: {n_converted} converted, {n_skipped} skipped")
    print(f"    Training:  {training_path}")
    print(f"    Metadata:  {metadata_path}")


def convert_all_splits(splits_dir: str, output_dir: str) -> None:
    """Convert all split files to Llama format."""
    splits_path = Path(splits_dir)
    print("\nConverting to Llama format:")

    for split_name in ["train", "val", "test"]:
        input_file = splits_path / f"{split_name}.jsonl"
        if input_file.exists():
            convert_file(str(input_file), output_dir, split_name)
        else:
            print(f"  {split_name}: not found")

    print(f"\nDone. Upload {output_dir}/*.jsonl (not *_metadata.jsonl) to GCS.")
    print(f"Keep *_metadata.jsonl locally for post-training slicing.")


# ══════════════════════════════════════════════
# RUN EVERYTHING
# ══════════════════════════════════════════════

if __name__ == "__main__":
    FILEPATH = r"C:\Users\vigne\Desktop\Higher studies\Northeastern University Boston\Courses\Spring 2026\MLOps\Project\ResearchLineage\timeline_view\outputs\lineage_training_data_v1.jsonl"
    SPLITS_DIR = "./lineage_splits"
    LLAMA_DIR = "./lineage_llama_format"

    # Step 1: Split
    print("=" * 60)
    print("STEP 1: SPLITTING DATASET")
    print("=" * 60)
    splits, df, samples = split_dataset(
        filepath=FILEPATH,
        train_frac=0.60,
        val_frac=0.20,
        test_frac=0.20,
        export_dir=SPLITS_DIR,
        seed=42,
    )

    # Step 2: Convert
    print("\n" + "=" * 60)
    print("STEP 2: CONVERTING TO LLAMA FORMAT")
    print("=" * 60)
    convert_all_splits(SPLITS_DIR, LLAMA_DIR)