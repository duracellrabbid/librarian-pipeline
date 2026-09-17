"""Application configuration and environment settings management using Pydantic Settings."""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application settings
    app_name: str = Field(default="rag-ingestion-pipeline", description="Application Name")
    environment: str = Field(default="development", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging level")
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 prefix")
    max_batch_ingest_size: int = Field(
        default=10,
        ge=1,
        description="Maximum number of documents allowed per batch ingestion request",
    )
    allowed_domains: list[str] = Field(
        default_factory=lambda: ["https://en.wikipedia.org"],
        description="List of allowed full-URL domain prefixes for document ingestion",
    )

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def _parse_allowed_domains(cls, value: Any) -> list[str] | Any:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [d.strip() for d in value.split(",") if d.strip()]
        return value

    # PostgreSQL configuration
    postgres_user: str = Field(default="postgres", description="PostgreSQL user")
    postgres_password: str = Field(default="postgres", description="PostgreSQL password")
    postgres_db: str = Field(default="rag_pipeline", description="PostgreSQL database name")
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL port")
    database_url: str | None = Field(default=None, description="Async database connection URL")
    sync_database_url: str | None = Field(default=None, description="Sync database connection URL")

    # Redis configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    redis_url: str | None = Field(default=None, description="Redis connection URL")

    # Qdrant configuration
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, ge=1, le=65535, description="Qdrant HTTP port")
    qdrant_grpc_port: int = Field(default=6334, ge=1, le=65535, description="Qdrant gRPC port")
    qdrant_url: str | None = Field(default=None, description="Qdrant base URL")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant API Key")

    # ARQ Worker configuration
    arq_job_timeout: int = Field(
        default=900,
        ge=1,
        description="ARQ background job timeout in seconds",
    )

    # Ollama configuration
    ollama_host: str = Field(default="localhost", description="Ollama host")
    ollama_port: int = Field(default=11434, ge=1, le=65535, description="Ollama port")
    ollama_base_url: str | None = Field(default=None, description="Ollama base URL")
    embedding_model: str = Field(default="bge-m3", description="Embedding model name")
    embedding_batch_size: int = Field(
        default=8,
        ge=1,
        description="Batch size for embedding generation requests",
    )
    embedding_timeout: float = Field(
        default=120.0,
        gt=0,
        description="HTTP timeout for embedding generation requests in seconds",
    )

    # Scraper and crawler configuration
    scraper_max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retry attempts for transient scraping errors",
    )
    scraper_backoff_factor: float = Field(
        default=1.5,
        gt=0,
        description="Exponential backoff base factor in seconds",
    )
    scraper_max_retry_delay: float = Field(
        default=60.0,
        gt=0,
        description="Maximum retry delay or Retry-After cap in seconds",
    )
    scraper_max_concurrency_per_domain: int = Field(
        default=2,
        ge=1,
        description="Maximum concurrent scraping requests per domain",
    )
    scraper_page_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Crawler page load timeout per attempt in seconds",
    )
    scraper_user_agent: str | None = Field(
        default=None,
        description="Custom User-Agent header identifying the scraper bot",
    )

    def model_post_init(self, __context: Any, /) -> None:
        """Construct dependent connection URLs if not explicitly provided."""
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
                f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.sync_database_url:
            self.sync_database_url = (
                f"postgresql://{self.postgres_user}:{self.postgres_password}@"
                f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
        if not self.qdrant_url:
            self.qdrant_url = f"http://{self.qdrant_host}:{self.qdrant_port}"
        if not self.ollama_base_url:
            self.ollama_base_url = f"http://{self.ollama_host}:{self.ollama_port}"
        if self.qdrant_api_key is not None and not self.qdrant_api_key.strip():
            self.qdrant_api_key = None
        if self.scraper_user_agent is not None and not self.scraper_user_agent.strip():
            self.scraper_user_agent = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()


settings = get_settings()
