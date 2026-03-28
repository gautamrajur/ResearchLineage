import os
import subprocess

import modal

app = modal.App(os.environ.get("MODAL_APP_NAME", "research-lineage-serving"))

# 1. FIXED: Use Modal's native image to bypass Docker Hub completely
image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1",
          "VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1" }) 
    .apt_install("git", "curl") # Modal's native apt installer
    .pip_install(               # Modal's native pip installer
        "vllm==0.6.3", 
        "fastapi==0.115.0", 
        "uvicorn==0.30.6", 
        "hf-transfer==0.1.8",
        "transformers==4.46.3", 
        "tokenizers==0.20.3"
    )
)

hf_volume = modal.Volume.from_name("model-cache", create_if_missing=True)

# 2. FIXED: Updated the GPU request syntax
@app.function(
    image=image,
    gpu="A100-80GB:2", 
    timeout=60 * 60,
    scaledown_window=300,
    volumes={"/root/.cache/huggingface": hf_volume}, 
)
@modal.concurrent(max_inputs=32)
@modal.web_server(8000, startup_timeout=600) 
def serve():
    serving_max_len = os.environ.get("SERVING_MAX_LEN", "102400").strip()
    hf_model_name = os.environ.get("HF_MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct-AWQ").strip()

    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--model", hf_model_name,
        "--max-model-len", serving_max_len,
        "--trust-remote-code",
        "--tensor-parallel-size", "2",     
        "--quantization", "awq",           
        "--dtype", "half",                 
        "--guided-decoding-backend", "lm-format-enforcer",
        "--enable-chunked-prefill=False",
        "--enforce-eager",
    ]

    print("Starting vLLM server:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)