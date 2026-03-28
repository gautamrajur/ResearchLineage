# src/evaluation/modal_app.py
"""
Modal app hosting three inference models for comparison:
  - Qwen2.5-7B-Instruct-AWQ
  - Llama-3.1-8B-Instruct-AWQ
  - Mistral-7B-Instruct-v0.3-AWQ

Deploy once with: poetry run modal deploy src/evaluation/modal_app.py

Endpoints printed after deploy:
  QwenModel.infer    => https://nekkantishiv--researchlineage-qwen-qwenmodel-infer.modal.run
  LlamaModel.infer   => https://nekkantishiv--researchlineage-qwen-llamamodel-infer.modal.run
  MistralModel.infer => https://nekkantishiv--researchlineage-qwen-mistralmodel-infer.modal.run
"""
from __future__ import annotations

import modal

app = modal.App("researchlineage-qwen")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.4.0",
        "huggingface_hub",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

# Separate persistent volumes per model so weights don't conflict
qwen_volume    = modal.Volume.from_name("qwen-weights",    create_if_missing=True)
llama_volume   = modal.Volume.from_name("llama-weights",   create_if_missing=True)
mistral_volume = modal.Volume.from_name("mistral-weights", create_if_missing=True)

MODEL_DIR = "/model-weights"
_SAMPLING_DEFAULTS = dict(
    max_tokens=8192,
    temperature=0.0,
    repetition_penalty=1.1,
    stop=["<|im_end|>", "<|endoftext|>", "</s>", "[/INST]"],
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
    "- breakthrough_level: must be exactly one of: 'minor', 'moderate', 'major'.\n"
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
    keep_warm=0,
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
            max_model_len=98304,  # 96K tokens — safe max for L40S 48GB with AWQ
        )

    @modal.web_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        from vllm import SamplingParams
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        formatted = (
            f"<|im_start|>system\n{_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
            "{\n"
        )
        outputs = self.llm.generate(
            [formatted],
            SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=_SAMPLING_DEFAULTS["repetition_penalty"],
                stop=_SAMPLING_DEFAULTS["stop"],
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
    keep_warm=0,
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
            max_model_len=98304,  # 96K tokens — safe max for L40S 48GB with AWQ
        )

    @modal.web_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        from vllm import SamplingParams
        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", _SAMPLING_DEFAULTS["max_tokens"])
        temperature = request.get("temperature", _SAMPLING_DEFAULTS["temperature"])

        # Llama 3.1 chat template
        formatted = (
            "<|begin_of_text|>"
            "<|start_header_id|>system<|end_header_id|>\n"
            f"{_SYSTEM_PROMPT}"
            "<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n"
            f"{prompt}"
            "<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n"
            "{\n"
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
    keep_warm=0,
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
            max_model_len=32768,  # Mistral hard limit is 32K
        )
        formatted = (
            f"<s>[INST] {_SYSTEM_PROMPT}\n\n{prompt} [/INST]\n"
            "{\n"
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