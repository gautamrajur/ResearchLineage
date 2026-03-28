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
        import time as _time

        import google.auth
        import google.auth.transport.requests
        import requests as req

        start = _time.monotonic()
        max_retries = 3
        retry_delays = [10, 30, 60]

        # Llama 3 Instruct requires chat template tokens
        formatted_prompt = (
            "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n"
            f"{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
        )

        for attempt in range(max_retries + 1):
            try:
                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                creds.refresh(google.auth.transport.requests.Request())

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
                latency_ms = (_time.monotonic() - start) * 1000
                logger.debug(
                    "VertexAI predict succeeded",
                    extra={"latency_ms": round(latency_ms, 1)},
                )

                if "Output:\n" in raw:
                    return raw.split("Output:\n", 1)[1].strip()
                return raw.strip()

            except Exception as exc:
                is_503 = "503" in str(exc)
                is_last = attempt == max_retries

                if is_last or not is_503:
                    latency_ms = (_time.monotonic() - start) * 1000
                    logger.error(
                        "Vertex AI predict call failed: %s", exc,
                        extra={"latency_ms": round(latency_ms, 1)},
                    )
                    raise

                delay = retry_delays[attempt]
                logger.warning(
                    f"503 on attempt {attempt + 1}/{max_retries} — "
                    f"retrying in {delay}s",
                    extra={"error": str(exc)},
                )
                _time.sleep(delay)

        raise RuntimeError("predict: exhausted retries")

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
        response_mime_type: str | None = None,
    ) -> None:
        # Use google-genai SDK (>=1.0) which works with both Vertex AI and AI Studio
        from google import genai
        from google.genai import types

        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

        self._client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )
        config_kwargs: dict = dict(temperature=temperature, max_output_tokens=max_output_tokens)
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type
        self._gen_config = types.GenerateContentConfig(**config_kwargs)

        logger.info(
            "GeminiClient initialised",
            extra={"model_name": model_name, "location": location},
        )

    def predict(self, prompt: str) -> str:
        max_retries = 4
        retry_delays = [10, 30, 60, 120]
        start = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=self._gen_config,
                )
                latency_ms = (time.monotonic() - start) * 1000
                logger.debug(
                    "Gemini predict succeeded",
                    extra={"latency_ms": round(latency_ms, 1)},
                )
                return response.text
            except Exception as exc:
                is_429 = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                is_last = attempt == max_retries

                if is_last or not is_429:
                    latency_ms = (time.monotonic() - start) * 1000
                    logger.error(
                        "Gemini predict call failed: %s", exc,
                        extra={"latency_ms": round(latency_ms, 1)},
                    )
                    raise

                delay = retry_delays[attempt]
                logger.warning(
                    "Gemini 429 on attempt %d/%d — retrying in %ds: %s",
                    attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)

        raise RuntimeError("predict: exhausted retries")

    def health_check(self) -> bool:
        try:
            self.predict("ping")
            return True
        except Exception as exc:
            logger.warning("Gemini health check failed", extra={"error": str(exc)})
            return False


# =============================================================== Modal client


class ModalClient(ModelClient):
    """
    Client for fine-tuned models served on Modal via vLLM (OpenAI-compatible /v1 API).
    Pass the base URL (with or without /v1) as endpoint_url.
    The served model name is auto-discovered from /v1/models on first call.
    """

    def __init__(
        self,
        endpoint_url: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 600.0,
    ) -> None:
        base = endpoint_url.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        self.base_url = base
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._model_name: str | None = None
        logger.info("ModalClient initialised", extra={"base_url": self.base_url})

    def _get_model_name(self) -> str:
        """Discover the first available model from /v1/models (cached after first call)."""
        if self._model_name:
            return self._model_name
        import requests as req
        resp = req.get(self.base_url + "/models", timeout=30)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        if not models:
            raise RuntimeError("No models returned by /v1/models")
        self._model_name = models[0]["id"]
        logger.info("ModalClient: discovered model %s", self._model_name)
        return self._model_name

    def predict(self, prompt: str) -> str:
        from openai import OpenAI

        start = time.monotonic()
        try:
            client = OpenAI(base_url=self.base_url, api_key="dummy", max_retries=0)
            response = client.chat.completions.create(
                model=self._get_model_name(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
            )
            text = response.choices[0].message.content or ""
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug("Modal predict succeeded", extra={"latency_ms": round(latency_ms, 1)})
            return text
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error("Modal predict failed: %s", exc, extra={"latency_ms": round(latency_ms, 1)})
            raise

    def health_check(self) -> bool:
        try:
            self._get_model_name()
            return True
        except Exception:
            return False


# =========================================== Factory — keeps callers import-clean


def build_inference_client(
    model_endpoint: str,
    project_id: str,
    location: str = "us-central1",
) -> ModelClient:
    """
    Build client for the inference model based on the endpoint string:
    - 'gemini-*'    → GeminiClient (managed Vertex AI Gemini API)
    - 'http*'       → ModalClient  (Modal web endpoint URL)
    - anything else → VertexAIClient (Vertex AI endpoint ID)
    """
    if model_endpoint.startswith("gemini-"):
        logger.info("Using GeminiClient for inference", extra={"model": model_endpoint})
        return GeminiClient(
            model_name=model_endpoint,
            project_id=project_id,
            location=location,
            max_output_tokens=8192,
            temperature=0.0,
        )
    if model_endpoint.startswith("http"):
        logger.info("Using ModalClient for inference", extra={"url": model_endpoint})
        return ModalClient(
            endpoint_url=model_endpoint,
            max_tokens=8192,
            temperature=0.0,
        )
    logger.info("Using VertexAIClient for inference", extra={"endpoint_id": model_endpoint})
    return VertexAIClient(
        endpoint_id=model_endpoint,
        project_id=project_id,
        location=location,
        max_output_tokens=8192,
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
