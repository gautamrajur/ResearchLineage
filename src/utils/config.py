"""Configuration management using Pydantic settings."""

from pathlib import Path
from typing import Set

from pydantic_settings import BaseSettings


# ========================================
# Pydantic Settings (from .env)
# ========================================

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API settings
    semantic_scholar_api_key: str = ""
    semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_rate_limit: int = 100
    semantic_scholar_request_timeout: int = 30
    semantic_scholar_max_retries: int = 15
    semantic_scholar_retry_base_wait: int = 1

    arxiv_base_url: str = "http://export.arxiv.org/api/query"
    openalex_base_url: str = "https://api.openalex.org"

    # Gemini settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.2
    gemini_max_output_tokens: int = 8192

    # Database settings
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "research_lineage"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 10

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_ttl: int = 172800

    # Pipeline settings
    max_citation_depth: int = 3
    max_papers_per_level: int = 5
    min_citation_count: int = 10
    influential_citation_weight: float = 2.0
    forward_citation_window: int = 3

    # GCS settings
    gcs_bucket_name: str = "researchlineage-gcs"
    gcs_project_id: str = "researchlineage"
    gcs_upload_prefix: str = "fine-tuning-artifacts/"

    # Monitoring
    log_level: str = "INFO"
    enable_metrics: bool = True
    verbose: bool = True

    # SMTP alert settings (anomaly detection + fetch_pdf_failures alerts)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_from: str = ""
    alert_email_to: str = ""

    # Environment
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()


# ========================================
# Logging
# ========================================

VERBOSE = settings.verbose


# ========================================
# Semantic Scholar API
# ========================================

S2_BASE_URL: str = settings.semantic_scholar_base_url
S2_API_KEY: str = settings.semantic_scholar_api_key
S2_REQUEST_TIMEOUT: int = settings.semantic_scholar_request_timeout
S2_MAX_RETRIES: int = settings.semantic_scholar_max_retries
S2_RETRY_BASE_WAIT: int = settings.semantic_scholar_retry_base_wait


# ========================================
# Gemini API
# ========================================

GEMINI_API_KEY: str = settings.gemini_api_key
GEMINI_MODEL: str = settings.gemini_model
GEMINI_TEMPERATURE: float = settings.gemini_temperature
GEMINI_MAX_OUTPUT_TOKENS: int = settings.gemini_max_output_tokens


# ========================================
# arXiv HTML Extraction
# ========================================

ARXIV_HTML_URLS = [
    "https://arxiv.org/html/{arxiv_id}",
    "https://ar5iv.org/html/{arxiv_id}",
]
HTML_REQUEST_TIMEOUT: int = 15


# ========================================
# Seed Generation (Step 1)
# ========================================

SEED_DOMAINS: list = ["Computer Science", "Physics", "Mathematics"]
SEED_MIN_CITATIONS: int = 5000
SEED_PER_DOMAIN_POOL: int = 800
SEED_DEFAULT_COUNT: int = 200
SEED_QUERY: str = "model | method | study | analysis"
SEED_RANDOM_SEED: int = 42


# ========================================
# Pipeline / Batch Run (Step 2)
# ========================================

MAX_DEPTH: int = 5
MAX_CANDIDATES: int = 10
MAX_SEEDS_PER_RUN: int = 50
BATCH_SLEEP_BETWEEN_SEEDS: float = 2.0


# ========================================
# Fine-Tuning (Step 5 — Split)
# ========================================

FINE_TUNING_ALLOWED_FIELDS: Set[str] = {
    "Computer Science",
    "Physics",
    "Mathematics",
}
SPLIT_TRAIN_FRAC: float = 0.70
SPLIT_VAL_FRAC: float = 0.15
SPLIT_TEST_FRAC: float = 0.15
SPLIT_RANDOM_SEED: int = 42


# ========================================
# GCS
# ========================================

GCS_BUCKET_NAME: str = settings.gcs_bucket_name
GCS_PROJECT_ID: str = settings.gcs_project_id
GCS_UPLOAD_PREFIX: str = settings.gcs_upload_prefix


# ========================================
# Paths — anchored to scripts/ directory
# ========================================

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/utils/config.py -> project root
RUN_DIR = _PROJECT_ROOT / "data" / "tasks" / "pipeline_output"

SEEDS_FILE: str = str(RUN_DIR / "seeds.json")
TRAINING_DATA_FILE: str = str(RUN_DIR / "training_data.jsonl")
REPAIRED_DATA_FILE: str = str(RUN_DIR / "training_data_repaired.jsonl")
SPLITS_DIR: str = str(RUN_DIR / "splits")
LLAMA_FORMAT_DIR: str = str(RUN_DIR / "llama_format")
TIMELINE_OUTPUT_DIR: str = str(RUN_DIR / "timelines")
STATE_FILE: str = str(RUN_DIR / "run_state.jsonl")
REPORT_JSON: str = str(RUN_DIR / "pipeline_report.json")
REPORT_TXT: str = str(RUN_DIR / "pipeline_report.txt")
LOG_FILE: str = str(RUN_DIR / "pipeline.log")


# ========================================
# Prompts
# ========================================

MAIN_PROMPT = """You are an expert research analyst specializing in tracing the methodological lineage of scientific papers.

## YOUR TASK

Given a TARGET paper and CANDIDATE predecessor papers (papers cited by the target), do three things:

### 1. SELECT THE PREDECESSOR
Identify which ONE candidate is the most direct methodological predecessor — the paper whose method/architecture/approach the target paper most directly builds upon, extends, or improves.

Selection criteria:
- Provided the core method/architecture that the target modifies or extends
- Explicitly described as the foundation in the target paper's introduction/methods
- Has the strongest "we build upon" or "we extend" relationship
- Is NOT just a technique used (like dropout, batch norm) but the main conceptual ancestor

Also identify secondary influences — other candidates that contributed meaningfully but aren't the primary predecessor.

### 2. ANALYZE THE TARGET PAPER
Provide a structured analysis with three levels of explanation:
- ELI5: Explain like the reader is 5 years old, using simple analogies
- Intuitive: For someone with basic ML/CS knowledge
- Technical: For researchers in the field, with specific technical details

### 3. COMPARE TARGET WITH PREDECESSOR
Explain exactly how the target improved upon the selected predecessor.

## OUTPUT FORMAT

Respond ONLY with valid JSON in this exact structure:

{
    "selected_predecessor_id": "<paperId of the chosen predecessor>",
    "selection_reasoning": "<2-3 sentences: why this paper over the others>",

    "secondary_influences": [
        {
            "paper_id": "<paperId>",
            "contribution": "<One sentence: what this paper contributed to the target>"
        }
    ],

    "target_analysis": {
        "problem_addressed": "<What specific problem does this paper solve?>",
        "core_method": "<Core approach/methodology in 2-3 sentences>",
        "key_innovation": "<What is genuinely new — the single most important contribution>",
        "limitations": ["<limitation 1>", "<limitation 2>", "<limitation 3>"],
        "breakthrough_level": "<revolutionary|major|moderate|minor>",
        "explanation_eli5": "<3-4 sentence explanation a child could understand, use analogies>",
        "explanation_intuitive": "<4-6 sentence explanation for someone with basic ML knowledge>",
        "explanation_technical": "<6-8 sentence detailed explanation for researchers, include technical specifics>"
    },

    "comparison": {
        "what_was_improved": "<Specific thing that changed from predecessor to target>",
        "how_it_was_improved": "<Technical details of the improvement>",
        "why_it_matters": "<Impact and significance of this improvement>",
        "problem_solved_from_predecessor": "<Which specific limitation of the predecessor was addressed>",
        "remaining_limitations": ["<What problems still remain after this improvement>"]
    }
}

## IMPORTANT RULES
- Select exactly ONE predecessor
- If a candidate only has abstract (marked ABSTRACT_ONLY), work with what you have
- Be specific and concrete — avoid vague statements like "improved performance"
- CITATION CONTEXTS show how the target paper references each candidate — use these as strong evidence for selection
- DOMAIN CONSISTENCY: The predecessor must be in the same research domain/problem area as the TARGET paper. For example, if the target paper is about machine translation, the predecessor should also address machine translation or a closely related task (like sequence-to-sequence modeling). Do NOT trace lineage into unrelated problem domains (like discourse analysis, speech recognition, image classification) just because the architecture or model structure is similar. The methodological lineage should follow the PROBLEM being solved, not just the neural network architecture used.
- If no candidate is a clear methodological predecessor in the same domain, prefer the candidate that is closest in problem domain, even if it is not the most architecturally similar.
- For breakthrough_level, use these strict criteria:

  "revolutionary" — Changed how the entire field works. Created a new paradigm that most 
  subsequent work builds on. Introduced a new concept or term that became standard vocabulary.
  The field can be divided into "before" and "after" this paper.
  Signal: 10,000+ citations, nearly all subsequent work in the subfield references it.
  Examples: Transformer, Backpropagation, AlexNet, GANs.

  "major" — Significant advance that became widely adopted. Solved a fundamental limitation 
  of prior work that was a known blocker. Introduced a technique that became a standard 
  component in later systems.
  Signal: 1,000-10,000 citations, commonly referenced as a key building block.
  Examples: Attention mechanism, ResNet, LSTM, Batch Normalization.

  "moderate" — Solid improvement on existing methods. Adopted by some researchers but didn't 
  change the overall field direction. Improved performance meaningfully but used similar 
  underlying principles.
  Signal: 200-1,000 citations, referenced in related work sections but not foundational.
  Examples: GRU, Layer Normalization, specific Seq2Seq variants.

  "minor" — Incremental improvement or variant. Small modification to existing approach.
  Useful but could be substituted with alternatives without major impact.
  Signal: Under 200 citations, rarely referenced outside its specific niche.
  Examples: Minor architecture tweaks, hyperparameter studies, small dataset contributions.
"""

FOUNDATIONAL_PROMPT = """You are an expert research analyst. Analyze this foundational research paper.

This paper is at the ROOT of a research lineage — it is the earliest paper in the chain. There is no predecessor to compare against.

## YOUR TASK

Provide a structured analysis with three levels of explanation.

## OUTPUT FORMAT

Respond ONLY with valid JSON in this exact structure:

{
    "target_analysis": {
        "problem_addressed": "<What specific problem does this paper solve?>",
        "core_method": "<Core approach/methodology in 2-3 sentences>",
        "key_innovation": "<What is genuinely new — the single most important contribution>",
        "limitations": ["<limitation 1>", "<limitation 2>", "<limitation 3>"],
        "breakthrough_level": "<revolutionary|major|moderate|minor>",
        "explanation_eli5": "<3-4 sentence explanation a child could understand, use analogies>",
        "explanation_intuitive": "<4-6 sentence explanation for someone with basic ML knowledge>",
        "explanation_technical": "<6-8 sentence detailed explanation for researchers, include technical specifics>"
    }
}

## IMPORTANT RULES
- This is a foundational paper — evaluate its contribution in the context of when it was published
- Be specific and concrete
- If only abstract is available (marked ABSTRACT_ONLY), work with what you have
- For breakthrough_level, use these strict criteria:

  "revolutionary" — Changed how the entire field works. Created a new paradigm that most 
  subsequent work builds on. Introduced a new concept or term that became standard vocabulary.
  The field can be divided into "before" and "after" this paper.
  Signal: 10,000+ citations, nearly all subsequent work in the subfield references it.

  "major" — Significant advance that became widely adopted. Solved a fundamental limitation 
  of prior work that was a known blocker. Introduced a technique that became a standard 
  component in later systems.
  Signal: 1,000-10,000 citations, commonly referenced as a key building block.

  "moderate" — Solid improvement on existing methods. Adopted by some researchers but didn't 
  change the overall field direction.
  Signal: 200-1,000 citations, referenced in related work sections but not foundational.

  "minor" — Incremental improvement or variant. Small modification to existing approach.
  Signal: Under 200 citations, rarely referenced outside its specific niche.
"""