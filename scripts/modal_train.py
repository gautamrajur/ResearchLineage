import gc
import json
import os
import time
from pathlib import Path

import modal

app = modal.App("research-lineage-a100")

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .run_commands(
        "apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*",
        "pip install --upgrade pip",
    )
    .run_commands(
        "pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121 --force-reinstall",
        "python -c \"import torch; print(torch.__version__); assert torch.__version__.startswith('2.4')\"",
    )
    .run_commands(
        "pip install accelerate==0.34.0",
        "pip install bitsandbytes==0.43.3",
        "pip install peft==0.12.0",
        "pip install trl==0.11.1",  # ← bumped from 0.8.6
    )
    .run_commands(
        "pip install protobuf==3.20.3",
        # ← bump unsloth to a version that works with transformers 4.46
        "pip install unsloth==2024.11.10 unsloth_zoo==2024.11.8 --no-deps",    )

    .run_commands(
        "pip install transformers==4.46.3",  # ← bumped, fixes tokenizer.json
        "pip install tokenizers==0.20.3",    # ← matches transformers 4.46
        "pip install datasets rich",
        "pip install huggingface-hub==0.26.2",
        "pip install google-cloud-storage==2.10.0",
        "pip install torchao==0.4.0",
        "pip install xformers==0.0.28.post1 --index-url https://download.pytorch.org/whl/cu121",
    )
)

# Local paths inside Modal container
LOCAL_TRAIN = Path("/tmp/train.jsonl")
LOCAL_VAL = Path("/tmp/val.jsonl")
LOCAL_MERGED = Path("/tmp/model_final")
LOCAL_METRICS = Path("/tmp/training_metrics.json")


def _upload_dir(bucket, local_dir: Path, output_path: str):
    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(local_dir).as_posix()
            blob = bucket.blob(f"{output_path.rstrip('/')}/{rel_path}")
            blob.upload_from_filename(str(file_path))


@app.function(
    gpu="A100-80GB",
    image=image,
    timeout=60 * 60 * 10,
    secrets=[modal.Secret.from_name("googlecloud-secret")],
)
def run_research_lineage(
    bucket_name: str,
    train_blob: str,
    val_blob: str = "",
    output_path: str = "models/trained/dev",
    max_seq_len: int = 102400,
):
    import torch
    from datasets import load_dataset
    from google.cloud import storage
    from google.oauth2 import service_account
    from trl import SFTTrainer
    from unsloth import FastLanguageModel
    from transformers import TrainingArguments
    from transformers import AutoTokenizer


    
    print(f"torch={torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    import bitsandbytes as bnb
    print(f"bitsandbytes={bnb.__version__}")


    # Memory-oriented env settings
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    os.environ["UNSLOTH_RETURN_TOKENIZER"] = "True"

    # ---- GCS auth from Modal secret ----
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)

    print("=" * 80)
    print("ResearchLineage long-context fine-tuning on Modal")
    print(f"Bucket      : {bucket_name}")
    print(f"Train blob  : {train_blob}")
    print(f"Val blob    : {val_blob or 'N/A'}")
    print(f"Output path : {output_path}")
    print(f"Max seq len : {max_seq_len}")
    print("=" * 80)

    # ---- Download data ----
    LOCAL_TRAIN.parent.mkdir(parents=True, exist_ok=True)
    bucket.blob(train_blob).download_to_filename(str(LOCAL_TRAIN))
    print(f"Downloaded train set to {LOCAL_TRAIN}")

    if val_blob:
        bucket.blob(val_blob).download_to_filename(str(LOCAL_VAL))
        print(f"Downloaded val set to {LOCAL_VAL}")


    # ---- Load model ----
    # 100k is experimental and expensive; this keeps it configurable.
    print("\nLoading base model with Unsloth...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/Qwen2.5-7B-Instruct",
        max_seq_length=max_seq_len,
        load_in_4bit=True,
        dtype=None,
        )
    
    # Prevent accelerate from upcasting to fp32
    import accelerate
    accelerate.utils.operations.convert_to_fp32 = lambda x: x

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],  # ← missing MLP layers
        lora_alpha=16,
        lora_dropout=0,                          # ← missing
        bias="none",
        use_gradient_checkpointing="unsloth",    # ← critical for 100k context
        random_state=3407,                       # ← missing
        use_rslora=False,
        loftq_config=None,
    )

    # ---- Load datasets ----
    print("\nLoading datasets...")
    train_dataset = load_dataset("json", data_files=str(LOCAL_TRAIN), split="train")
    eval_dataset = None
    if val_blob and LOCAL_VAL.exists():
        eval_dataset = load_dataset("json", data_files=str(LOCAL_VAL), split="train")

    print(f"Train rows: {len(train_dataset)}")
    if eval_dataset is not None:
        print(f"Val rows  : {len(eval_dataset)}")

    



    training_args = TrainingArguments(
        output_dir="outputs",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=64,
        num_train_epochs=3,        # ← replace max_steps=60
        learning_rate=2e-4,
        bf16=True,
        logging_steps=1,
        optim="paged_adamw_8bit",
        save_strategy="no",
        bf16_full_eval=True,        # ← add this
        dataloader_pin_memory=False, # ← add this
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_len,
        args=training_args,
    )

    # ---- Train ----
    print("\nStarting training...")
    start_time = time.time()
    trainer.train()
    elapsed_min = (time.time() - start_time) / 60.0
    print(f"Training complete in {elapsed_min:.2f} minutes")

    # ---- Pull last loss from log history ----
    final_loss = None
    eval_loss = None
    if getattr(trainer.state, "log_history", None):
        for item in reversed(trainer.state.log_history):
            if final_loss is None and "loss" in item:
                final_loss = item["loss"]
            if eval_loss is None and "eval_loss" in item:
                eval_loss = item["eval_loss"]
            if final_loss is not None and eval_loss is not None:
                break

    # ---- Merge and save ----
    print("\nMerging adapter into 16-bit model...")
    LOCAL_MERGED.mkdir(parents=True, exist_ok=True)
    model.save_pretrained_merged(
        str(LOCAL_MERGED),
        tokenizer,
        save_method="merged_16bit",
    )

    # ---- Metrics ----
    metrics = {
        "training_status": "success",
        "training_minutes": elapsed_min,
        "final_loss": final_loss if final_loss is not None else "N/A",
        "eval_loss": eval_loss if eval_loss is not None else "N/A",
        "max_seq_length": max_seq_len,
        "max_steps": 60,
        "learning_rate": 2e-4,
        "gradient_accumulation_steps": 64,
        "per_device_train_batch_size": 1,
        "train_rows": len(train_dataset),
        "val_rows": len(eval_dataset) if eval_dataset is not None else 0,
        "base_model": "unsloth/Qwen2.5-7B-Instruct",
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(LOCAL_METRICS, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # ---- Upload merged model + metrics ----
    print(f"\nUploading merged model to gs://{bucket_name}/{output_path}")
    _upload_dir(bucket, LOCAL_MERGED, output_path)

    metrics_blob = bucket.blob(f"{output_path.rstrip('/')}/training_metrics.json")
    metrics_blob.upload_from_filename(str(LOCAL_METRICS))
    print("Uploaded training_metrics.json")

    # ---- Cleanup ----
    del trainer
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print("\nDone.")
    return {
        "status": "ok",
        "output_path": output_path,
        "max_seq_length": max_seq_len,
        "training_minutes": elapsed_min,
    }

@app.local_entrypoint()
def main(
    bucket_name: str,
    train_blob: str,
    val_blob: str = "",
    output_path: str = "models/trained/dev",
    max_seq_len: int = 102400,
):
    run_research_lineage.remote(
        bucket_name=bucket_name,
        train_blob=train_blob,
        val_blob=val_blob,
        output_path=output_path,
        max_seq_len=max_seq_len,
    )