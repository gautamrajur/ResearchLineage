# scripts/debug_config.py
"""
Prints the resolved config values to verify project IDs are correct.
Run with: poetry run python scripts/debug_config.py
"""
from dotenv import load_dotenv

from src.evaluation.config import EvaluationConfig

load_dotenv()

cfg = EvaluationConfig()

print(f"gcs_project_id         : {cfg.gcs_project_id}")
print(f"vertex_project_id      : {cfg.vertex_project_id}")
print(f"judge_project_id       : {cfg.judge_project_id}")
print(f"vertex_endpoint_id     : {cfg.vertex_endpoint_id}")
print(f"judge_endpoint_id      : '{cfg.judge_endpoint_id}'")
print(f"judge_model_name       : {cfg.judge_model_name}")
print(f"vertex_location        : {cfg.vertex_location}")
print(f"gcs_input_path         : {cfg.gcs_input_path}")
print(f"gcs_output_path        : {cfg.gcs_output_path}")
print()
print(f"Effective inference project : {cfg.vertex_project_id or cfg.gcs_project_id}")
print(f"Effective judge project     : {cfg.judge_project_id or cfg.gcs_project_id}")