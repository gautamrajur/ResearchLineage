FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

WORKDIR /app

# 1. System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Build-time variables for L4 (Compute Capability 8.9)
ENV TORCH_CUDA_ARCH_LIST="8.9"
ENV MAX_JOBS=4 

# 3. Install requirements with root-user safety
COPY docker/requirements-training.txt /requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --root-user-action=ignore -r /requirements.txt

# 4. App code
COPY scripts/train.py /app/train.py

# 5. Final check: Verify installation via pip only. 
# DO NOT import unsloth here as Cloud Build lacks a GPU.
RUN pip show unsloth && pip show xformers && echo "✅ Unsloth & xformers verified"

ENTRYPOINT ["python", "/app/train.py"]