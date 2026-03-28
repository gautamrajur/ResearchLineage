FROM apache/airflow:2.8.1-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install packages needed by the evaluation DAG
# google-cloud-aiplatform includes vertexai + Gemini client support
RUN pip install --no-cache-dir \
    "google-cloud-aiplatform>=1.49.0" \
    "google-cloud-storage>=2.14.0" \
    "google-genai>=1.0.0" \
    "pydantic-settings>=2.0.0" \
    "numpy" \
    "beautifulsoup4" \
    "requests"
