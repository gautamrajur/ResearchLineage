import json
import os
import requests
import time

TRAINING_FILE = os.path.join("outputs_jitin", "lineage_training_data_v4.jsonl")
S2_BASE = "https://api.semanticscholar.org/graph/v1"


def main():
    if not os.path.exists(TRAINING_FILE):
        print("No training data found.")
        return

    # Step 1: Read all entries
    entries = []
    with open(TRAINING_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    # Step 2: Collect all unique paper IDs
    paper_ids = set()
    for entry in entries:
        li = entry.get("level_info", {})

        tp = li.get("target_paper", {})
        if tp.get("paper_id"):
            paper_ids.add(tp["paper_id"])

        pp = li.get("predecessor_paper") or {}
        if pp.get("paper_id"):
            paper_ids.add(pp["paper_id"])

        for c in li.get("candidates_passed_to_llm", []):
            if c.get("paper_id"):
                paper_ids.add(c["paper_id"])

    print(f"📊 Found {len(paper_ids)} unique papers in {len(entries)} entries")

    # Step 3: Batch fetch raw s2FieldsOfStudy from S2
    id_list = list(paper_ids)
    # Maps paper_id -> raw list exactly as API returns it
    fields_map = {}

    for i in range(0, len(id_list), 500):
        batch = id_list[i:i+500]
        print(f"   Fetching batch {i//500 + 1} ({len(batch)} papers)...")

        for attempt in range(5):
            try:
                resp = requests.post(
                    f"{S2_BASE}/paper/batch",
                    json={"ids": batch},
                    params={"fields": "paperId,s2FieldsOfStudy"},
                    timeout=30
                )

                if resp.status_code == 200:
                    for paper in resp.json():
                        if paper and paper.get("paperId"):
                            # Store raw array exactly as returned — no filtering
                            fields_map[paper["paperId"]] = paper.get("s2FieldsOfStudy") or []
                    break
                elif resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    print(f"   ⚠️  Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"   ❌ Error {resp.status_code}: {resp.text[:200]}")
                    break
            except Exception as e:
                print(f"   ❌ Request failed: {e}")
                time.sleep(5)

        time.sleep(2)

    print(f"   Got fields for {len(fields_map)} papers")

    # Step 4: Overwrite s2_fields_of_study with raw API array for every paper
    updated = 0
    for entry in entries:
        li = entry.get("level_info", {})

        tp = li.get("target_paper", {})
        if tp.get("paper_id") and tp["paper_id"] in fields_map:
            tp["s2_fields_of_study"] = fields_map[tp["paper_id"]]
            updated += 1

        pp = li.get("predecessor_paper") or {}
        if pp.get("paper_id") and pp["paper_id"] in fields_map:
            pp["s2_fields_of_study"] = fields_map[pp["paper_id"]]
            updated += 1

        for c in li.get("candidates_passed_to_llm", []):
            if c.get("paper_id") and c["paper_id"] in fields_map:
                c["s2_fields_of_study"] = fields_map[c["paper_id"]]
                updated += 1

    # Step 5: Write back
    with open(TRAINING_FILE, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"✅ Overwrote s2_fields_of_study for {updated} paper entries in JSONL")


if __name__ == "__main__":
    main()