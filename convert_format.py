import json
import os

BASE_PATH = r"C:\Users\vigne\Desktop\Higher studies\Northeastern University Boston\Courses\Spring 2026\MLOps\Project"

splits = ["train", "val", "test"]

for split in splits:
    input_path  = os.path.join(BASE_PATH, f"{split}.jsonl")
    output_path = os.path.join(BASE_PATH, f"{split}_converted.jsonl")

    converted = 0
    skipped   = 0

    with open(input_path, encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                input_text  = record.get("input_text", "")
                output_text = record.get("output_text", "")

                if not input_text or not output_text:
                    skipped += 1
                    continue

                text = (
                    f"<|im_start|>user\n{input_text}<|im_end|>\n"
                    f"<|im_start|>assistant\n{output_text}<|im_end|>"
                )
                fout.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
                converted += 1

            except json.JSONDecodeError as e:
                print(f"  ⚠️  Skipping bad line: {e}")
                skipped += 1

    print(f"✅ {split}: {converted} converted, {skipped} skipped → {output_path}")

print("\nDone! Upload these files to GCS:")
for split in splits:
    print(f"  {os.path.join(BASE_PATH, f'{split}_converted.jsonl')}")