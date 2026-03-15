# src/evaluation/model_client.py
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ================================================================== Base class


class ModelClient(ABC):
    """
    Abstract base for any model used in this pipeline — inference or judge.
    Swap the implementation without touching any evaluator.
    """

    @abstractmethod
    def predict(self, prompt: str) -> str:
        """Send prompt, return raw string response."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the endpoint is reachable."""
        ...


# ============================================================== Vertex AI client


class VertexAIClient(ModelClient):
    """
    Client for a Model Garden Llama endpoint.
    Calls the prediction REST API directly using google-auth credentials
    to avoid SDK URL routing issues with mg-endpoint-style endpoint IDs.
    """

    def __init__(
        self,
        endpoint_id: str,
        project_id: str,
        location: str = "us-central1",
        max_output_tokens: int = 2048,
        temperature: float = 0.0,
        timeout: float = 300.0,
    ) -> None:
        self.endpoint_id = endpoint_id
        self.project_id = project_id
        self.location = location
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._url = (
            f"https://{location}-prediction-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/"
            f"endpoints/{endpoint_id}:predict"
        )

        logger.info(
            "VertexAIClient initialised",
            extra={"endpoint_id": endpoint_id, "location": location},
        )

    def predict(self, prompt: str) -> str:
        import google.auth
        import google.auth.transport.requests
        import requests as req

        start = time.monotonic()
        try:
            # refresh credentials
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(google.auth.transport.requests.Request())

            # Llama 3 Instruct requires chat template tokens
            formatted_prompt = (
                "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n"
                f"{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
            )

            response = req.post(
                self._url,
                json={
                    "instances": [
                        {
                            "prompt": formatted_prompt,
                            "max_tokens": self.max_output_tokens,
                            "temperature": self.temperature,
                        }
                    ]
                },
                headers={
                    "Authorization": f"Bearer {creds.token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            preds = response.json().get("predictions", [])
            if not preds:
                raise ValueError("Empty predictions from endpoint.")

            raw = str(preds[0])

            latency_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "VertexAI predict succeeded",
                extra={"latency_ms": round(latency_ms, 1)},
            )

            # extract Output section from "Prompt:\n...\nOutput:\n..."
            if "Output:\n" in raw:
                return raw.split("Output:\n", 1)[1].strip()
            return raw.strip()

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "Vertex AI predict call failed",
                extra={"latency_ms": round(latency_ms, 1), "error": str(exc)},
            )
            raise

    def health_check(self) -> bool:
        try:
            self.predict("ping")
            return True
        except Exception as exc:
            logger.warning("Health check failed", extra={"error": str(exc)})
            return False


# ================================================================ Gemini client


class GeminiClient(ModelClient):
    """
    Client for Gemini models served as managed APIs on Vertex AI.
    No endpoint deployment needed — call directly by model name.
    e.g. model_name = "gemini-2.5-flash"
    """

    def __init__(
        self,
        model_name: str,
        project_id: str,
        location: str = "us-central1",
        max_output_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> None:
        import vertexai
        from vertexai.generative_models import GenerationConfig, GenerativeModel

        self.model_name = model_name
        self.project_id = project_id
        self.location = location
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

        vertexai.init(project=project_id, location=location)

        self._model = GenerativeModel(model_name)
        self._generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        logger.info(
            "GeminiClient initialised",
            extra={"model_name": model_name, "location": location},
        )

    def predict(self, prompt: str) -> str:
        start = time.monotonic()
        try:
            response = self._model.generate_content(
                prompt,
                generation_config=self._generation_config,
            )
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "Gemini predict succeeded",
                extra={"latency_ms": round(latency_ms, 1)},
            )
            return response.text
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "Gemini predict call failed",
                extra={"latency_ms": round(latency_ms, 1), "error": str(exc)},
            )
            raise

    def health_check(self) -> bool:
        try:
            self.predict("ping")
            return True
        except Exception as exc:
            logger.warning("Gemini health check failed", extra={"error": str(exc)})
            return False


# =========================================== Factory — keeps callers import-clean


def build_inference_client(
    endpoint_id: str,
    project_id: str,
    location: str = "us-central1",
) -> ModelClient:
    """Build client for the fine-tuned model on a Vertex AI endpoint."""
    return VertexAIClient(
        endpoint_id=endpoint_id,
        project_id=project_id,
        location=location,
        max_output_tokens=2048,
        temperature=0.0,
    )


def build_judge_client(
    project_id: str,
    location: str = "us-central1",
    model_name: str = "gemini-2.5-flash",
    max_output_tokens: int = 1024,
    temperature: float = 0.0,
    endpoint_id: str | None = None,
) -> ModelClient:
    """
    Build judge client.
    - If endpoint_id is None: uses GeminiClient (managed API).
    - If endpoint_id is provided: uses VertexAIClient (custom endpoint).
    """
    if endpoint_id:
        return VertexAIClient(
            endpoint_id=endpoint_id,
            project_id=project_id,
            location=location,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
    return GeminiClient(
        model_name=model_name,
        project_id=project_id,
        location=location,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
