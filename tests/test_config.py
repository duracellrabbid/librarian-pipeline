import pytest
from pydantic import ValidationError


def test_default_settings():
    """Verify default settings instantiate with expected defaults."""
    from app.core.config import Settings

    settings = Settings()
    assert settings.app_name == "rag-ingestion-pipeline"
    assert settings.environment == "development"
    assert settings.postgres_port == 5432
    assert "postgresql+asyncpg" in settings.database_url
    assert settings.redis_port == 6379
    assert settings.qdrant_port == 6333
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.embedding_model == "bge-m3"
    assert settings.max_batch_ingest_size == 10
    assert settings.allowed_domains == ["https://en.wikipedia.org"]
    assert settings.arq_job_timeout == 900
    assert settings.embedding_batch_size == 8
    assert settings.embedding_timeout == 120.0
    assert settings.scraper_max_retries == 3
    assert settings.scraper_backoff_factor == 1.5
    assert settings.scraper_max_retry_delay == 60.0
    assert settings.scraper_max_concurrency_per_domain == 2
    assert settings.scraper_page_timeout == 30.0
    assert settings.scraper_user_agent is None


def test_derived_connection_urls():
    """Verify that connection URLs are derived when not explicitly provided."""
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        database_url=None,
        sync_database_url=None,
        redis_url=None,
        qdrant_url=None,
        ollama_base_url=None,
    )
    assert settings.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_pipeline"
    assert settings.sync_database_url == "postgresql://postgres:postgres@localhost:5432/rag_pipeline"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.ollama_base_url == "http://localhost:11434"


def test_env_override(monkeypatch):
    """Verify environment variables override defaults properly."""
    from app.core.config import Settings

    monkeypatch.setenv("APP_NAME", "custom-pipeline")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embed-v1")
    monkeypatch.setenv("QDRANT_URL", "http://custom-qdrant:6333")
    monkeypatch.setenv("MAX_BATCH_INGEST_SIZE", "25")
    monkeypatch.setenv("ARQ_JOB_TIMEOUT", "1200")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "4")
    monkeypatch.setenv("EMBEDDING_TIMEOUT", "60.0")
    monkeypatch.setenv("ALLOWED_DOMAINS", '["https://example.org"]')
    monkeypatch.setenv("SCRAPER_MAX_RETRIES", "5")
    monkeypatch.setenv("SCRAPER_BACKOFF_FACTOR", "2.0")
    monkeypatch.setenv("SCRAPER_MAX_RETRY_DELAY", "90.0")
    monkeypatch.setenv("SCRAPER_MAX_CONCURRENCY_PER_DOMAIN", "4")
    monkeypatch.setenv("SCRAPER_PAGE_TIMEOUT", "45.0")
    monkeypatch.setenv("SCRAPER_USER_AGENT", "CustomBot/1.0 (test@example.com)")

    settings = Settings()
    assert settings.app_name == "custom-pipeline"
    assert settings.environment == "production"
    assert settings.postgres_port == 5433
    assert settings.redis_port == 6380
    assert settings.embedding_model == "custom-embed-v1"
    assert settings.qdrant_url == "http://custom-qdrant:6333"
    assert settings.max_batch_ingest_size == 25
    assert settings.arq_job_timeout == 1200
    assert settings.embedding_batch_size == 4
    assert settings.embedding_timeout == 60.0
    assert settings.allowed_domains == ["https://example.org"]
    assert settings.scraper_max_retries == 5
    assert settings.scraper_backoff_factor == 2.0
    assert settings.scraper_max_retry_delay == 90.0
    assert settings.scraper_max_concurrency_per_domain == 4
    assert settings.scraper_page_timeout == 45.0
    assert settings.scraper_user_agent == "CustomBot/1.0 (test@example.com)"


def test_invalid_port_validation(monkeypatch):
    """Verify validation error when port is invalid."""
    from app.core.config import Settings

    monkeypatch.setenv("POSTGRES_PORT", "not-a-number")
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_batch_size_validation(monkeypatch):
    """Verify validation error when max_batch_ingest_size is invalid or non-positive."""
    from app.core.config import Settings

    monkeypatch.setenv("MAX_BATCH_INGEST_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("MAX_BATCH_INGEST_SIZE", "not-a-number")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_singleton():
    """Verify get_settings returns a cached instance."""
    from app.core.config import get_settings

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_dotenv_example_load():
    """Verify that settings can be loaded from .env.example without errors."""
    from app.core.config import Settings
    from dotenv import dotenv_values

    env_example = dotenv_values(".env.example")
    assert len(env_example) > 0
    # Clean empty values
    clean_values = {k: v for k, v in env_example.items() if v}
    settings = Settings(**clean_values)
    assert settings.postgres_db == "rag_pipeline"
    assert settings.embedding_model == "bge-m3"
    assert settings.max_batch_ingest_size == 10


def test_empty_qdrant_api_key_normalized_to_none(monkeypatch):
    """Verify that empty or whitespace QDRANT_API_KEY is normalized to None."""
    from app.core.config import Settings

    monkeypatch.setenv("QDRANT_API_KEY", "")
    settings = Settings()
    assert settings.qdrant_api_key is None

    monkeypatch.setenv("QDRANT_API_KEY", "   ")
    settings_ws = Settings()
    assert settings_ws.qdrant_api_key is None

    monkeypatch.setenv("QDRANT_API_KEY", "valid-secret-key")
    settings_valid = Settings()
    assert settings_valid.qdrant_api_key == "valid-secret-key"


def test_empty_scraper_user_agent_normalized_to_none(monkeypatch):
    """Verify that empty or whitespace SCRAPER_USER_AGENT is normalized to None."""
    from app.core.config import Settings

    monkeypatch.setenv("SCRAPER_USER_AGENT", "")
    settings = Settings()
    assert settings.scraper_user_agent is None

    monkeypatch.setenv("SCRAPER_USER_AGENT", "   ")
    settings_ws = Settings()
    assert settings_ws.scraper_user_agent is None

    monkeypatch.setenv("SCRAPER_USER_AGENT", "CustomBot/1.0")
    settings_valid = Settings()
    assert settings_valid.scraper_user_agent == "CustomBot/1.0"


def test_invalid_new_settings_validation(monkeypatch):
    """Verify validation error when new settings have non-positive or invalid values."""
    from app.core.config import Settings

    monkeypatch.setenv("ARQ_JOB_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("ARQ_JOB_TIMEOUT", "900")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "8")
    monkeypatch.setenv("EMBEDDING_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_scraper_settings_validation(monkeypatch):
    """Verify validation errors when scraper settings violate constraints."""
    from app.core.config import Settings

    monkeypatch.setenv("SCRAPER_MAX_RETRIES", "-1")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SCRAPER_MAX_RETRIES", "3")
    monkeypatch.setenv("SCRAPER_BACKOFF_FACTOR", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SCRAPER_BACKOFF_FACTOR", "1.5")
    monkeypatch.setenv("SCRAPER_MAX_RETRY_DELAY", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SCRAPER_MAX_RETRY_DELAY", "60.0")
    monkeypatch.setenv("SCRAPER_MAX_CONCURRENCY_PER_DOMAIN", "0")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("SCRAPER_MAX_CONCURRENCY_PER_DOMAIN", "2")
    monkeypatch.setenv("SCRAPER_PAGE_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_parse_allowed_domains_formats():
    """Verify string formats parse properly when supplied to Settings."""
    from app.core.config import Settings

    settings_json = Settings(allowed_domains='["https://site1.org", "https://site2.org"]')
    assert settings_json.allowed_domains == ["https://site1.org", "https://site2.org"]

    settings_csv = Settings(allowed_domains="https://site1.org, https://site2.org")
    assert settings_csv.allowed_domains == ["https://site1.org", "https://site2.org"]

    # Malformed JSON with bracket fallback
    settings_malformed = Settings(allowed_domains="[not-valid-json]")
    assert settings_malformed.allowed_domains == ["[not-valid-json]"]
