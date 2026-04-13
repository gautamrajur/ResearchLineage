# src/evaluation/modal_app.py
"""
Modal app hosting inference models for ResearchLineage evaluation:
  - Qwen2.5-7B-Instruct-AWQ     (single L40S, vLLM native)
  - Llama-3.1-8B-Instruct-AWQ   (single L40S, vLLM native)
  - Mistral-7B-Instruct-v0.3-AWQ(single L40S, vLLM native)
  - Llama-3.1-70B-Instruct-AWQ  (2x A100-80GB, vLLM subprocess + tensor parallelism)

Deploy: poetry run modal deploy src/evaluation/modal_app.py
"""
from __future__ import annotations

import subprocess
import time

import modal

app = modal.App("researchlineage-qwen")

# ------------------------------------------------------------------ images

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.4.0",
        "huggingface_hub",
        "hf_transfer",
        "requests",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1",
    })
)

image_70b = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl")
    .pip_install(
        "vllm==0.6.3",
        "hf-transfer==0.1.8",
        "transformers==4.46.3",
        "tokenizers==0.20.3",
        "requests",
        "pyairports",  # required by outlines (vLLM guided decoding dependency)
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1",
    })
)

# ------------------------------------------------------------------ volumes

qwen_volume     = modal.Volume.from_name("qwen-weights",     create_if_missing=True)
llama_volume    = modal.Volume.from_name("llama-weights",    create_if_missing=True)
mistral_volume  = modal.Volume.from_name("mistral-weights",  create_if_missing=True)
llama70b_volume = modal.Volume.from_name("llama70b-weights", create_if_missing=True)

MODEL_DIR = "/model-weights"

# ------------------------------------------------------------------ shared config

_SAMPLING_DEFAULTS = dict(
    max_tokens=8192,
    temperature=0.0,
    repetition_penalty=1.1,
)

_SYSTEM_PROMPT = (
    "You are an expert scientific research analyst. "
    "Your task is to analyze academic papers and their citation relationships.\n\n"

    "## OUTPUT RULES\n"
    "- Respond ONLY with a single valid JSON object. No markdown, no explanation, no text outside the JSON.\n"
    "- Do NOT wrap your response in ```json``` fences.\n"
    "- Every field in the schema is REQUIRED. Never omit a field.\n"
    "- Use null (not the string 'null') for missing values where the type is nullable.\n"
    "- Use empty string \"\" for missing string fields, [] for missing list fields.\n\n"

    "## FIELD RULES\n"
    "- selected_predecessor_id: must be one of the candidate paper IDs provided, or null if none match.\n"
    "- selection_reasoning: must explain WHY this predecessor was chosen based on methodology, not just topic.\n"
    "- secondary_influences: list of objects with paper_id and contribution fields. Use [] if none.\n"
    "- breakthrough_level: must be exactly one of: 'minor', 'moderate', 'major', 'revolutionary'.\n"
    "- explanation_eli5: explain as if to a 10-year-old. Must be non-empty.\n"
    "- explanation_intuitive: conceptual explanation without jargon. Must be non-empty.\n"
    "- explanation_technical: precise technical explanation. Must be non-empty.\n"
    "- All comparison fields (what_was_improved, how_it_was_improved, why_it_matters, "
    "problem_solved_from_predecessor) must be non-empty strings.\n\n"

    "## GUARDRAILS\n"
    "- Do NOT hallucinate paper IDs. Only use IDs explicitly provided in the input.\n"
    "- Do NOT copy text verbatim from the input. Summarize and analyse in your own words.\n"
    "- Do NOT include any fields not in the schema.\n"
    "- If you are uncertain about a field, provide your best analysis rather than leaving it empty.\n"
    "- All JSON keys and string values must use properly escaped double quotes.\n"
    "- Never omit commas between JSON fields or array elements.\n"
)


# ================================================================== Qwen2.5-7B


@app.cls(
    gpu="L40S",
    image=image,
    volumes={MODEL_DIR: qwen_volume},
    timeout=600,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    min_containers=0,
    scaledown_window=60,
)
class QwenModel:
    MODEL_ID = "Qwen/Qwen2.5-7B-Instruct-AWQ"

    @modal.enter()
    def load_model(self) -> None:
        from vllm import LLM
        self.llm = LLM(
            model=self.MODEL_ID,
            download_dir=MODEL_DIR,
            quantization="awq",
            dtype="float16",
            max_model_len=98304,
        )

    @modal.fastapi_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        from vllm import SamplingParams
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        formatted = (
            f"<|im_start|>system\n{_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n{\n"
        )
        outputs = self.llm.generate(
            [formatted],
            SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=_SAMPLING_DEFAULTS["repetition_penalty"],
                stop=["<|im_end|>", "<|endoftext|>"],
            ),
        )
        text = "{" + outputs[0].outputs[0].text.strip()
        return {"text": text, "model": self.MODEL_ID}


# ================================================================== Llama-3.1-8B


@app.cls(
    gpu="L40S",
    image=image,
    volumes={MODEL_DIR: llama_volume},
    timeout=600,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    min_containers=0,
    scaledown_window=60,
)
class LlamaModel:
    MODEL_ID = "hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4"

    @modal.enter()
    def load_model(self) -> None:
        from vllm import LLM
        self.llm = LLM(
            model=self.MODEL_ID,
            download_dir=MODEL_DIR,
            quantization="awq",
            dtype="float16",
            max_model_len=98304,
        )

    @modal.fastapi_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        from vllm import SamplingParams
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        formatted = (
            "<|begin_of_text|>"
            "<|start_header_id|>system<|end_header_id|>\n"
            f"{_SYSTEM_PROMPT}"
            "<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n"
            f"{prompt}"
            "<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n{\n"
        )
        outputs = self.llm.generate(
            [formatted],
            SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=_SAMPLING_DEFAULTS["repetition_penalty"],
                stop=["<|eot_id|>", "<|end_of_text|>"],
            ),
        )
        text = "{" + outputs[0].outputs[0].text.strip()
        return {"text": text, "model": self.MODEL_ID}


# ================================================================== Mistral-7B


@app.cls(
    gpu="L40S",
    image=image,
    volumes={MODEL_DIR: mistral_volume},
    timeout=600,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    min_containers=0,
    scaledown_window=60,
)
class MistralModel:
    MODEL_ID = "TheBloke/Mistral-7B-Instruct-v0.3-AWQ"

    @modal.enter()
    def load_model(self) -> None:
        from vllm import LLM
        self.llm = LLM(
            model=self.MODEL_ID,
            download_dir=MODEL_DIR,
            quantization="awq",
            dtype="float16",
            max_model_len=32768,
        )

    @modal.fastapi_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        from vllm import SamplingParams
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        formatted = (
            f"<s>[INST] {_SYSTEM_PROMPT}\n\n{prompt} [/INST]\n{{\n"
        )
        outputs = self.llm.generate(
            [formatted],
            SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=_SAMPLING_DEFAULTS["repetition_penalty"],
                stop=["</s>", "[/INST]"],
            ),
        )
        text = "{" + outputs[0].outputs[0].text.strip()
        return {"text": text, "model": self.MODEL_ID}


# ================================================================== Llama-3.1-70B (2x A100-80GB)


@app.cls(
    gpu="A100-80GB:2",
    image=image_70b,
    volumes={MODEL_DIR: llama70b_volume},
    timeout=1200,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    min_containers=0,
    scaledown_window=300,
)
class Qwen72BModel:
    MODEL_ID = "Qwen/Qwen2.5-72B-Instruct-AWQ"
    VLLM_PORT = 8000

    @modal.enter()
    def load_model(self) -> None:
        import requests

        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--host", "0.0.0.0",
            "--port", str(self.VLLM_PORT),
            "--model", self.MODEL_ID,
            "--download-dir", MODEL_DIR,
            "--max-model-len", "98304",
            "--tensor-parallel-size", "2",
            "--quantization", "awq",
            "--dtype", "half",
            "--trust-remote-code",
            "--enforce-eager",
            "--enable-chunked-prefill=False",
            "--guided-decoding-backend", "lm-format-enforcer",
        ]
        print("Starting vLLM server:", " ".join(cmd))
        self._vllm_proc = subprocess.Popen(cmd)

        # wait for vLLM to be ready (up to 10 min for 70B)
        for attempt in range(120):
            try:
                resp = requests.get(
                    f"http://localhost:{self.VLLM_PORT}/health",
                    timeout=5,
                )
                if resp.status_code == 200:
                    print(f"vLLM ready after {attempt * 5}s")
                    return
            except Exception:
                pass
            time.sleep(5)
        raise RuntimeError("vLLM server failed to start within 10 minutes")

    @modal.fastapi_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        import requests as req

        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        formatted = (
            f"<|im_start|>system\n{_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n{\n"
        )

        response = req.post(
            f"http://localhost:{self.VLLM_PORT}/v1/completions",
            json={
                "model": self.MODEL_ID,
                "prompt": formatted,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "repetition_penalty": _SAMPLING_DEFAULTS["repetition_penalty"],
                "stop": ["<|im_end|>", "<|endoftext|>"],
            },
            timeout=300,
        )
        response.raise_for_status()
        text = "{" + response.json()["choices"][0]["text"].strip()
        return {"text": text, "model": self.MODEL_ID}