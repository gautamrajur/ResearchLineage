#!/bin/bash
set -e

python3 -m vllm.entrypoints.openai.api_server \
    --model /model \
    --quantization awq \
    --dtype half \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.90 \
    --host 0.0.0.0 \
    --port ${PORT} \
    --served-model-name qwen2.5-7b-awq
