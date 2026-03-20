# src/evaluation/modal_app.py
"""
Modal app that hosts Qwen2.5-7B-AWQ via vLLM.
Deploy once with: poetry run modal deploy src/evaluation/modal_app.py
Then call from ModalClient in model_client.py.
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

# Persistent volume so weights are downloaded once and reused across deploys.
volume = modal.Volume.from_name("qwen-weights", create_if_missing=True)
MODEL_DIR = "/model-weights"
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct-AWQ"


@app.cls(
    gpu="L40S",
    image=image,
    volumes={MODEL_DIR: volume},
    timeout=600,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    keep_warm=0,
)
class QwenModel:
    @modal.enter()
    def load_model(self) -> None:
        """Called once when the container starts — loads model into GPU memory."""
        from vllm import LLM

        self.llm = LLM(
            model=MODEL_ID,
            download_dir=MODEL_DIR,
            quantization="awq",
            dtype="float16",
            max_model_len=32768,
        )

    @modal.web_endpoint(method="POST")
    def infer(self, request: dict) -> dict:
        """
        Web endpoint — accepts {"prompt": str, "max_tokens": int, "temperature": float}
        Returns {"text": str, "model": str}
        """
        from vllm import SamplingParams

        prompt = request.get("prompt", "")
        max_tokens = request.get("max_tokens", 512)
        temperature = request.get("temperature", 0.0)

        # Wrap in Qwen chat template with strict guardrails
        formatted = (
            "<|im_start|>system\n"
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
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"{prompt}"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "{\n"  # prime the model to start the JSON object immediately
        )

        outputs = self.llm.generate(
            [formatted],
            SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=1.1,
                stop=["<|im_end|>", "<|endoftext|>"],
            ),
        )
        # Prepend the opening brace we used as a primer
        text = "{" + outputs[0].outputs[0].text.strip()
        return {"text": text, "model": MODEL_ID}