"""Inference client for deployed fine-tuned models.

Uses Application Default Credentials (ADC) — no service account key file.

Before running:
    gcloud auth application-default login

Usage:
    python -m temporary.ft_infer --endpoint ENDPOINT_RESOURCE_NAME --prompt "Hello"
    python -m temporary.ft_infer --endpoint ENDPOINT_RESOURCE_NAME --interactive
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from google.cloud import aiplatform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _init_vertex():
    """Initialise Vertex AI using ADC."""
    from temporary.ft_custom_config import CustomTrainConfig
    cfg = CustomTrainConfig()
    aiplatform.init(project=cfg.project_id, location=cfg.region)
    return cfg


def predict(
    endpoint_name: str,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """Send a prediction request to a deployed endpoint.

    Args:
        endpoint_name: Endpoint resource name
        prompt: Input prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Generated response string
    """
    _init_vertex()

    endpoint = aiplatform.Endpoint(endpoint_name=endpoint_name)
    instance = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    response = endpoint.predict(instances=[instance])
    if response.predictions:
        return response.predictions[0]
    return ""


def interactive_chat(endpoint_name: str) -> None:
    """Start an interactive chat session with the deployed model."""
    print("\n" + "=" * 50)
    print("Interactive Chat with Fine-tuned Llama 3")
    print("=" * 50)
    print("Type 'quit' to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if user_input.lower() in ("quit", "exit"):
                print("Goodbye!")
                break
            if not user_input:
                continue
            response = predict(endpoint_name, user_input)
            print(f"Model: {response}\n")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Inference client for fine-tuned Llama 3 on Vertex AI"
    )
    parser.add_argument("--endpoint", type=str, required=True,
                        help="Endpoint resource name")
    parser.add_argument("--prompt", type=str, help="Single prompt")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive chat mode")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.7)

    args = parser.parse_args()

    if args.interactive:
        interactive_chat(args.endpoint)
    elif args.prompt:
        response = predict(
            endpoint_name=args.endpoint,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        print(f"\nResponse: {response}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
