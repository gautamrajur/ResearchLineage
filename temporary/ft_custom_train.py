"""Training script for Llama 3 LoRA fine-tuning using Model Garden weights.

Runs INSIDE the Vertex AI custom training container.

Key design decisions:
- Weights loaded from /gcs/<bucket>/... (GCS FUSE mount on Vertex AI VMs)
- No HuggingFace token required — uses Google-hosted weights
- No evaluation during training (no eval_strategy)
- ADC provides credentials automatically inside the container

GCS FUSE mount: gs://bucket/path → /gcs/bucket/path
The conversion is handled by gcs_to_fuse() before any file I/O.

Launch with:  python ft_custom_job.py --launch
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def gcs_to_fuse(path: str) -> str:
    """Convert a gs:// URI to the /gcs/ FUSE mount path used on Vertex AI VMs.

    gs://my-bucket/path/to/file  →  /gcs/my-bucket/path/to/file
    """
    if path.startswith("gs://"):
        return path.replace("gs://", "/gcs/", 1)
    return path  # already a local path


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    """Load a JSONL file. filepath may be a /gcs/ path."""
    samples = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def format_for_llama(sample: Dict[str, str]) -> str:
    """Format a sample for Llama 3 instruction fine-tuning.

    Expected input keys: "input" and "output"
    (produced by ft_data_prep.py from the pipeline's input_text/output_text).
    """
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")

    return (
        "<|begin_of_text|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{input_text}"
        "<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{output_text}"
        "<|eot_id|>"
    )


def prepare_dataset(
    data_path: str,
    tokenizer,
    max_length: int = 2048,
) -> Dataset:
    """Load, format, and tokenize a JSONL dataset.

    data_path may be a /gcs/ path (GCS FUSE).
    """
    samples = load_jsonl(data_path)
    logger.info("Loaded %d samples from %s", len(samples), data_path)

    formatted = [{"text": format_for_llama(s)} for s in samples]
    dataset = Dataset.from_list(formatted)

    def tokenize_function(examples):
        # No return_tensors here — HuggingFace Datasets handles that via the collator
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )

    tokenized = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=["text"],
    )
    logger.info("Tokenized dataset: %d samples", len(tokenized))
    return tokenized


def setup_model_and_tokenizer(model_path: str, use_4bit: bool = True):
    """Load model and tokenizer from a /gcs/ FUSE path.

    model_path should already be a /gcs/ path (call gcs_to_fuse() before this).
    No HuggingFace token required.
    """
    logger.info("Loading model from: %s", model_path)

    bnb_config = None
    if use_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    if use_4bit:
        model = prepare_model_for_kbit_training(model)

    logger.info("Model loaded: %s", model.config.model_type)
    return model, tokenizer


def setup_lora(
    model,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    target_modules: Optional[List[str]] = None,
):
    """Attach a LoRA adapter to the model."""
    if target_modules is None:
        target_modules = [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ]

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info("Trainable params: %s (%.2f%%)", f"{trainable:,}", 100 * trainable / total)
    return model


def train(
    model,
    tokenizer,
    train_dataset: Dataset,
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 4,
    gradient_accumulation_steps: int = 4,
    learning_rate: float = 2e-4,
    warmup_ratio: float = 0.03,
    weight_decay: float = 0.01,
    save_steps: int = 100,
    logging_steps: int = 10,
):
    """Run training. output_dir may be a /gcs/ path (GCS FUSE)."""
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        warmup_ratio=warmup_ratio,
        weight_decay=weight_decay,
        logging_steps=logging_steps,
        save_steps=save_steps,
        save_total_limit=3,
        # No evaluation
        do_eval=False,
        bf16=True,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        report_to=["tensorboard"],
        logging_dir=f"{output_dir}/logs",
    )

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator,
    )

    logger.info("Starting training...")
    trainer.train()

    logger.info("Saving model to %s", output_dir)
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save the LoRA adapter separately for lightweight deployment
    adapter_dir = os.path.join(output_dir, "lora_adapter")
    model.save_pretrained(adapter_dir)
    logger.info("LoRA adapter saved to %s", adapter_dir)

    return trainer


def main():
    parser = argparse.ArgumentParser(description="Llama 3 LoRA fine-tuning (Model Garden, ADC)")

    parser.add_argument("--train-data", type=str, required=True,
                        help="gs:// URI for training JSONL")
    parser.add_argument("--val-data", type=str, default=None,
                        help="gs:// URI for validation JSONL (unused — no eval)")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="gs:// URI for output artifacts")
    parser.add_argument("--model-path", type=str, required=True,
                        help="gs:// URI to Model Garden weights")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--use-4bit", action="store_true", default=False,
                        help="Enable 4-bit QLoRA quantization")

    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)

    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--logging-steps", type=int, default=10)

    args = parser.parse_args()

    # Convert all gs:// URIs to /gcs/ FUSE mount paths
    model_fuse = gcs_to_fuse(args.model_path)
    train_fuse = gcs_to_fuse(args.train_data)
    output_fuse = gcs_to_fuse(args.output_dir)

    logger.info("=" * 60)
    logger.info("Llama 3 LoRA Fine-tuning (Model Garden + ADC)")
    logger.info("Model (FUSE): %s", model_fuse)
    logger.info("Train data (FUSE): %s", train_fuse)
    logger.info("Output (FUSE): %s", output_fuse)
    logger.info("4-bit QLoRA: %s", args.use_4bit)
    logger.info("=" * 60)

    model, tokenizer = setup_model_and_tokenizer(model_fuse, use_4bit=args.use_4bit)
    model = setup_lora(
        model,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
    )

    train_dataset = prepare_dataset(train_fuse, tokenizer, max_length=args.max_length)

    train(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        output_dir=output_fuse,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        save_steps=args.save_steps,
        logging_steps=args.logging_steps,
    )

    logger.info("Training complete! Artifacts at: %s", args.output_dir)


if __name__ == "__main__":
    main()
