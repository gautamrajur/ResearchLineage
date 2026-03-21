"""Vertex AI Model Garden: utilities for Llama 3 models.

This module provides information about supported Llama 3 models
available in GCP Model Garden for Managed SFT.
"""
from __future__ import annotations

from typing import Dict, Any, List

# Supported Llama 3 models for Managed SFT with their specifications
SUPPORTED_MODELS: Dict[str, Dict[str, Any]] = {
    "meta/llama3_1@llama-3.1-8b": {
        "display_name": "Llama 3.1 8B",
        "tuning_modes": ["PEFT_ADAPTER", "FULL"],
        "max_seq_length": {"PEFT_ADAPTER": 4096, "FULL": 8192},
        "description": "Base Llama 3.1 8B model",
    },
    "meta/llama3_1@llama-3.1-8b-instruct": {
        "display_name": "Llama 3.1 8B Instruct",
        "tuning_modes": ["PEFT_ADAPTER", "FULL"],
        "max_seq_length": {"PEFT_ADAPTER": 4096, "FULL": 8192},
        "description": "Instruction-tuned Llama 3.1 8B",
    },
    "meta/llama3-2@llama-3.2-1b-instruct": {
        "display_name": "Llama 3.2 1B Instruct",
        "tuning_modes": ["FULL"],
        "max_seq_length": {"FULL": 8192},
        "description": "Lightweight Llama 3.2 1B instruction model",
    },
    "meta/llama3-2@llama-3.2-3b-instruct": {
        "display_name": "Llama 3.2 3B Instruct",
        "tuning_modes": ["FULL"],
        "max_seq_length": {"FULL": 8192},
        "description": "Lightweight Llama 3.2 3B instruction model",
    },
    "meta/llama3-3@llama-3.3-70b-instruct": {
        "display_name": "Llama 3.3 70B Instruct",
        "tuning_modes": ["PEFT_ADAPTER", "FULL"],
        "max_seq_length": {"PEFT_ADAPTER": 4096, "FULL": 8192},
        "description": "Large Llama 3.3 70B instruction model",
    },
}


def list_supported_models() -> List[str]:
    """List all supported Model Garden IDs."""
    return list(SUPPORTED_MODELS.keys())


def get_model_info(model_id: str) -> Dict[str, Any]:
    """Get information about a model.
    
    Args:
        model_id: Model Garden ID
        
    Returns:
        Model info dictionary or empty dict if not found
    """
    return SUPPORTED_MODELS.get(model_id, {})


def is_lora_supported(model_id: str) -> bool:
    """Check if LoRA (PEFT_ADAPTER) is supported for a model.
    
    Args:
        model_id: Model Garden ID
        
    Returns:
        True if LoRA is supported
    """
    info = get_model_info(model_id)
    if not info:
        return False
    return "PEFT_ADAPTER" in info.get("tuning_modes", [])


def print_supported_models() -> None:
    """Print all supported models with details."""
    print("\n" + "=" * 70)
    print("Supported Llama 3 Models in GCP Model Garden")
    print("=" * 70)
    
    for model_id, info in SUPPORTED_MODELS.items():
        lora_supported = "✅" if "PEFT_ADAPTER" in info["tuning_modes"] else "❌"
        print(f"\n{info['display_name']}")
        print(f"  Model ID: {model_id}")
        print(f"  LoRA Support: {lora_supported}")
        print(f"  Tuning Modes: {', '.join(info['tuning_modes'])}")
        print(f"  Description: {info['description']}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    print_supported_models()
