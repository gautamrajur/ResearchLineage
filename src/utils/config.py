"""Configuration management using Pydantic settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API settings
    semantic_scholar_api_key: str = ""
    semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_rate_limit: int = 100

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
    max_papers_per_level: int = 15
    min_citation_count: int = 10
    influential_citation_weight: float = 2.0

    # Monitoring
    log_level: str = "INFO"
    enable_metrics: bool = True

    # Environment
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
