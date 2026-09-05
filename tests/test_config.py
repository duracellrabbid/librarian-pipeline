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


def test_env_override(monkeypatch):
    """Verify environment variables override defaults properly."""
    from app.core.config import Settings

    monkeypatch.setenv("APP_NAME", "custom-pipeline")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embed-v1")
    monkeypatch.setenv("QDRANT_URL", "http://custom-qdrant:6333")

    settings = Settings()
    assert settings.app_name == "custom-pipeline"
    assert settings.environment == "production"
    assert settings.postgres_port == 5433
    assert settings.redis_port == 6380
    assert settings.embedding_model == "custom-embed-v1"
    assert settings.qdrant_url == "http://custom-qdrant:6333"


def test_invalid_port_validation(monkeypatch):
    """Verify validation error when port is invalid."""
    from app.core.config import Settings

    monkeypatch.setenv("POSTGRES_PORT", "not-a-number")
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
