## 1. Project Initialization & Packaging

- [x] 1.1 Create `pyproject.toml` with dependencies (`fastapi`, `uvicorn`, `pydantic-settings`, `sqlmodel`, `asyncpg`, `alembic`, `redis`, `arq`, `qdrant-client`, `crawl4ai`, `httpx`, `pytest`, `pytest-asyncio`).
- [x] 1.2 Create application package directory structure (`app/core`, `app/models`, `app/services`, `app/workers`, `app/api`) with initial `__init__.py` files.
- [x] 1.3 Create `.gitignore` ignoring virtual environments, `.env`, caches, and data directories.

## 2. Infrastructure Configuration

- [x] 2.1 Create `docker-compose.yml` with services for PostgreSQL 16, Redis 7, Qdrant, and Ollama with persistent named volumes and health checks.
- [x] 2.2 Create `.env.example` defining all required connection URLs, ports, and configuration keys.

## 3. Configuration Management & Validation

- [x] 3.1 Implement `app/core/config.py` using `pydantic-settings` to parse and validate environment variables.
- [x] 3.2 Create a connectivity check script (`scripts/check_env.py`) to verify reachability of PostgreSQL, Redis, Qdrant, and Ollama.
- [x] 3.3 Add unit test in `tests/test_config.py` verifying configuration loading and validation behavior.
