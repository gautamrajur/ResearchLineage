FROM apache/airflow:2.8.1-python3.11

USER root

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python dependencies
RUN pip install --no-cache-dir \
    google-cloud-build \
    psycopg2-binary \
    httpx \
    networkx \
    redis \
    great-expectations \
    alembic \
    python-dotenv \
    pydantic \
    pydantic-settings \
    apache-airflow-providers-google \
    google-cloud-aiplatform \
    google-cloud-storage \
    pandas \
    pyarrow \
    modal

# Copy source code
COPY --chown=airflow:root src/ /opt/airflow/src/
COPY --chown=airflow:root dags/ /opt/airflow/dags/