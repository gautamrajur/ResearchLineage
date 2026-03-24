import json
import os
import subprocess
from pathlib import Path

import modal

app = modal.App(os.environ.get("MODAL_APP_NAME", "research-lineage-serving"))

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .run_commands(
        "apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*",
        "pip install --upgrade pip",
        "pip install vllm==0.6.3 fastapi==0.115.0 uvicorn==0.30.6 google-cloud-storage==2.10.0",
        "pip install transformers==4.46.3 tokenizers==0.20.3", 
    )
)

model_volume = modal.Volume.from_name("model-cache", create_if_missing=True)
CACHE_DIR = Path("/model-cache")


def _download_gcs_dir(gcs_uri: str, local_dir: Path):
    from google.cloud import storage
    from google.oauth2 import service_account

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")

    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    client = storage.Client(credentials=credentials)

    path = gcs_uri.replace("gs://", "", 1)
    bucket_name, prefix = path.split("/", 1)
    prefix = prefix.rstrip("/") + "/"

    bucket = client.bucket(bucket_name)
    local_dir.mkdir(parents=True, exist_ok=True)

    found_any = False
    for blob in bucket.list_blobs(prefix=prefix):
        rel = blob.name[len(prefix):]
        if not rel:
            continue
        found_any = True
        dest = local_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(dest))

    if not found_any:
        raise FileNotFoundError(f"No files found under {gcs_uri}")


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=60 * 60,
    scaledown_window=300,
    volumes={"/model-cache": model_volume},
    secrets=[
        modal.Secret.from_name("googlecloud-secret"),
        modal.Secret.from_name("serving-config"),
    ],
)
@modal.concurrent(max_inputs=32)
@modal.web_server(8000, startup_timeout=300)
def serve():
    model_path = os.environ.get("MODEL_GCS_PATH", "").strip()
    serving_max_len = os.environ.get("SERVING_MAX_LEN", "102400").strip()
    hf_model_name = os.environ.get("HF_MODEL_NAME", "").strip()

    if not model_path and not hf_model_name:
        raise ValueError("Set MODEL_GCS_PATH or HF_MODEL_NAME in the serving-config secret.")

    if model_path:
        version = model_path.rstrip("/").split("/")[-1]
        cache_dir = CACHE_DIR / version

        if not cache_dir.exists():
            print(f"Cache miss — downloading model from {model_path}")
            _download_gcs_dir(model_path, cache_dir)
            model_volume.commit()
            print("Model cached to volume.")
        else:
            print(f"Cache hit — using {cache_dir}")

        model_arg = str(cache_dir)
    else:
        model_arg = hf_model_name

    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--model", model_arg,
        "--max-model-len", serving_max_len,
        "--trust-remote-code",
        "--dtype", "bfloat16",
        "--guided-decoding-backend", "lm-format-enforcer",
        "--enable-chunked-prefill=False",
        "--enforce-eager",
    ]

    print("Starting vLLM server:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)