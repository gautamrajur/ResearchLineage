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

                # DEBUG — remove once 503 is resolved
                print(f"DEBUG URL: {self._url}")
                print(f"DEBUG project_id: {self.project_id}")
                print(f"DEBUG prompt[:100]: {formatted_prompt[:100]}")

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
                        "Vertex AI predict call failed",
                        extra={"latency_ms": round(latency_ms, 1), "error": str(exc)},
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


# ===================================================== OpenAI-compatible client


class OpenAIClient(ModelClient):
    """
    OpenAI Chat Completions API (v1) — works with vLLM, Modal OpenAI wrappers, etc.
    Expects base_url pointing at the API root (e.g. .../v1); the SDK appends
    /chat/completions as needed.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "dummy",
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 600.0,
        max_retries: int = 0,
    ) -> None:
        from openai import OpenAI

        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

        self._client = OpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

        logger.info(
            "OpenAIClient initialised",
            extra={"base_url": base_url, "model": model},
        )

    def predict(self, prompt: str) -> str:
        start = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            raw = response.choices[0].message.content
            text = (raw or "").strip()
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "OpenAI-compatible predict succeeded",
                extra={"latency_ms": round(latency_ms, 1)},
            )
            return text
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "OpenAI-compatible predict failed",
                extra={"latency_ms": round(latency_ms, 1), "error": str(exc)},
            )
            raise

    def health_check(self) -> bool:
        try:
            self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            return True
        except Exception as exc:
            logger.warning(
                "OpenAI-compatible health check failed",
                extra={"error": str(exc)},
            )
            return False


# =============================================================== Modal client


class ModalClient(ModelClient):
    """
    Client for Qwen2.5-7B-AWQ hosted on Modal via vLLM.
    After deploying modal_app.py, set the printed endpoint URL
    as MODAL_ENDPOINT_URL in your .env file.
    """

    def __init__(
        self,
        endpoint_url: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 600.0,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        logger.info(
            "ModalClient initialised",
            extra={"endpoint_url": endpoint_url},
        )

    def predict(self, prompt: str) -> str:
        import requests as req

        start = time.monotonic()
        try:
            response = req.post(
                self.endpoint_url,
                json={
                    "prompt": prompt,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = response.json().get("text", "")
            latency_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "Modal predict succeeded",
                extra={"latency_ms": round(latency_ms, 1)},
            )
            return text
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "Modal predict failed",
                extra={"latency_ms": round(latency_ms, 1), "error": str(exc)},
            )
            raise

    def health_check(self) -> bool:
        import requests as req

        try:
            response = req.post(
                self.endpoint_url,
                json={"prompt": "ping", "max_tokens": 1},
                timeout=600.0,
            )
            return response.status_code == 200
        except Exception:
            return False


# =========================================== Factory — keeps callers import-clean


def build_inference_client(
    endpoint_id: str,
    project_id: str,
    location: str = "us-central1",
    modal_endpoint_url: str | None = None,
    *,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
    openai_max_tokens: int = 8192,
    openai_timeout: float = 600.0,
    openai_temperature: float = 0.0,
    openai_max_retries: int = 0,
) -> ModelClient:
    """
    Build client for the inference model.
    - If openai_base_url and openai_model are set: OpenAIClient (highest priority).
    - Else if modal_endpoint_url is set: ModalClient (custom JSON prompt/text).
    - Otherwise: VertexAIClient.
    """
    has_openai = bool(openai_base_url or openai_model)
    if has_openai and not (openai_base_url and openai_model):
        raise ValueError(
            "OpenAI-compatible inference requires both openai_base_url and openai_model "
            "(set neither to use Modal or Vertex instead)."
        )
    if openai_base_url and openai_model:
        logger.info("Using OpenAIClient for inference")
        return OpenAIClient(
            base_url=openai_base_url,
            model=openai_model,
            api_key=openai_api_key or "dummy",
            max_tokens=openai_max_tokens,
            temperature=openai_temperature,
            timeout=openai_timeout,
            max_retries=openai_max_retries,
        )
    if modal_endpoint_url:
        logger.info("Using ModalClient for inference")
        return ModalClient(
            endpoint_url=modal_endpoint_url,
            max_tokens=8192,
            temperature=0.0,
        )
    logger.info("Using VertexAIClient for inference")
    return VertexAIClient(
        endpoint_id=endpoint_id,
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
