"""
scripts/train.py - Optimized Unsloth fine-tuning for ResearchLineage
Runs inside a Vertex AI Custom Training Job container.
"""

import gc
import json
import os
import time
from pathlib import Path

import torch
from datasets import Dataset
from google.cloud import storage
from unsloth import FastLanguageModel
from trl import SFTConfig, SFTTrainer

# Memory safety environment variables
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"
os.environ["UNSLOTH_RETURN_TOKENIZER"] = "True"

# ── Config from environment ───────────────────────────────────────────────────
GCS_BASE_MODEL  = os.environ["GCS_BASE_MODEL_PATH"]
GCS_TRAIN_DATA  = os.environ["GCS_TRAIN_DATA_PATH"]
GCS_VAL_DATA    = os.environ["GCS_VAL_DATA_PATH"]
GCS_OUTPUT      = os.environ["GCS_OUTPUT_PATH"]
MODEL_VERSION   = os.environ.get("MODEL_VERSION", "v1")

LOCAL_MODEL_DIR  = Path("/tmp/base_model")
LOCAL_TRAIN      = Path("/tmp/train.jsonl")
LOCAL_VAL        = Path("/tmp/val.jsonl")
LOCAL_ADAPTER    = Path("/tmp/adapter")
LOCAL_MERGED     = Path("/tmp/merged_model")

# ── GCS helpers ──────────────────────────────────────────────────────────────
def _gcs_client():
    return storage.Client()

def gcs_download_dir(gcs_path: str, local_path: Path):
    path = gcs_path.replace("gs://", "")
    bucket_name, prefix = path.split("/", 1)
    prefix = prefix.rstrip("/") + "/"
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    local_path.mkdir(parents=True, exist_ok=True)
    print(f"📥 Downloading base model files from {gcs_path}...")
    for blob in blobs:
        rel = blob.name[len(prefix):]
        if not rel: continue
        dest = local_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))
    print(f"✅ Downloaded to {local_path}")

def gcs_download_file(gcs_path: str, local_path: Path):
    path = gcs_path.replace("gs://", "")
    bucket_name, blob_name = path.split("/", 1)
    client = _gcs_client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.bucket(bucket_name).blob(blob_name).download_to_filename(str(local_path))
    print(f"✅ Downloaded {local_path.name}")

def gcs_upload_dir(local_path: Path, gcs_path: str):
    path = gcs_path.replace("gs://", "")
    bucket_name, prefix = path.split("/", 1)
    prefix = prefix.rstrip("/")
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    files = [f for f in local_path.rglob("*") if f.is_file()]
    print(f"📤 Uploading merged model to {gcs_path}...")
    for f in files:
        blob_name = f"{prefix}/{f.relative_to(local_path)}"
        bucket.blob(blob_name).upload_from_filename(str(f))
    print(f"✅ Uploaded to {gcs_path}")

# ── Data loading ──────────────────────────────────────────────────────────────
def load_jsonl(path: Path) -> Dataset:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return Dataset.from_list(records)

# ── Main ──────────────────────────────────────────────────────────────────────
def train():
    print("=" * 60)
    print(f"🔬 ResearchLineage Fine-tuning (Unsloth) — {MODEL_VERSION}")
    print("=" * 60)

    # Step 1 & 2: Data/Model Prep
    gcs_download_dir(GCS_BASE_MODEL, LOCAL_MODEL_DIR)
    gcs_download_file(GCS_TRAIN_DATA, LOCAL_TRAIN)
    gcs_download_file(GCS_VAL_DATA, LOCAL_VAL)

    # Step 4: Loading model via Unsloth
    print("\n🤖 Step 4: Loading model with Unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = str(LOCAL_MODEL_DIR),
        max_seq_length = 102400, # Set to your target 80k
        load_in_4bit = True,
        trust_remote_code = True,
        device_map = {"": 0},
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r = 16,
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj"],
        lora_alpha = 32,
        lora_dropout = 0, # Optimized for 0
        bias = "none",
        use_gradient_checkpointing = "unsloth", 
        random_state = 3407,
    )

    # Step 5: Load datasets
    train_dataset = load_jsonl(LOCAL_TRAIN)
    val_dataset   = load_jsonl(LOCAL_VAL)

    # Step 6: Training Configuration
    TRAINING_ARGS = SFTConfig(
    output_dir=str(LOCAL_ADAPTER),
    per_device_train_batch_size=1,
    gradient_accumulation_steps=64, # Increased for 100k stability
    learning_rate=2e-4,
    optim="paged_adamw_8bit",      # Crucial for 100k
    weight_decay=0.01,
    max_steps=60,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    gradient_checkpointing=True,    # Must be True for 100k
)

    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = train_dataset,
        eval_dataset = val_dataset,
        max_seq_length = 102400,
        args = TRAINING_ARGS,
    )

    print("\n🚀 Step 6: Starting training...")
    start_time = time.time()
    trainer.train()
    elapsed = (time.time() - start_time) / 60
    print(f"\n✅ Training complete in {elapsed:.1f} minutes")

    # Step 7: Saving & Merging
    # Unsloth's save_pretrained_merged handles the entire reload/merge flow safely
    print("\n💾 Step 7: Merging and Saving model (16-bit)...")
    model.save_pretrained_merged(str(LOCAL_MERGED), tokenizer, save_method = "merged_16bit")
    
    # Save training metrics
    metrics = {
        "model_version": MODEL_VERSION,
        "training_minutes": elapsed,
        "final_loss": trainer.state.log_history[-1].get("loss") if trainer.state.log_history else "N/A",
        "context_window": 102400
    }
    with open(LOCAL_MERGED / "training_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    # Step 9: Upload to GCS
    gcs_upload_dir(LOCAL_MERGED, GCS_OUTPUT)
    print(f"\n🎉 Done! Merged model saved to {GCS_OUTPUT}")

if __name__ == "__main__":
    train()