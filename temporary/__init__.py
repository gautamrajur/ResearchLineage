"""Fine-tuning module for ResearchLineage.

This module provides two approaches for Llama 3 LoRA fine-tuning:

1. MANAGED SFT (Original Approach) - ft_vertex_job.py
   - One API call, Google manages training
   - Limited control, strict data format
   - Weights stored as Vertex AI model endpoint
   
2. CUSTOM TRAINING (Recommended for DAGs) - ft_custom_job.py
   - Full control over training
   - Weights saved to GCS (you own them)
   - Better for Airflow DAG integration

Quick Start:
    
    # Managed SFT (simple, limited control)
    python -m temporary.ft_vertex_job --launch
    
    # Custom Training (recommended)
    python -m temporary.ft_data_prep --prepare --upload
    python -m temporary.ft_custom_job --launch --wait

For Airflow integration, see ft_airflow_tasks.py
"""

# Managed SFT (original approach)
from temporary.ft_config import FineTuneConfig
from temporary.ft_vertex_job import launch_managed_sft_job

# Custom Training (recommended for DAGs)
from temporary.ft_custom_config import CustomTrainConfig
from temporary.ft_data_prep import prepare_dataset, upload_to_gcs
from temporary.ft_custom_job import launch_custom_training_job

# Airflow tasks
from temporary.ft_airflow_tasks import (
    task_prepare_training_data,
    task_upload_to_gcs,
    task_launch_training,
    task_register_model,
)

__all__ = [
    # Config
    "FineTuneConfig",
    "CustomTrainConfig",
    # Managed SFT
    "launch_managed_sft_job",
    # Custom Training
    "prepare_dataset",
    "upload_to_gcs", 
    "launch_custom_training_job",
    # Airflow tasks
    "task_prepare_training_data",
    "task_upload_to_gcs",
    "task_launch_training",
    "task_register_model",
]
