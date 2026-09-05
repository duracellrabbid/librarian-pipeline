## Why

To support a modular, production-ready RAG ingestion pipeline on a single server, we must first establish a clean Python project foundation with dependency management, standardized directory structures, and a local Docker Compose infrastructure hosting PostgreSQL, Redis, Qdrant, and Ollama. Establishing this upfront guarantees a reliable runtime environment for all subsequent database, extraction, vector, and API phases.

## What Changes

- Initialize Python project management with `pyproject.toml` and lockfile/dependency setup.
- Define application directory structure (`app/core`, `app/models`, `app/services`, `app/workers`, `app/api`).
- Create `docker-compose.yml` for local single-server infrastructure:
  - **PostgreSQL 16**: Document registry and job tracking.
  - **Redis 7**: Message broker for async ARQ task queue.
  - **Qdrant**: Standalone vector database with persistent volume.
  - **Ollama**: Local container/daemon configuration with `bge-m3` model support.
- Implement centralized application settings (`app/core/config.py`) using `pydantic-settings` to validate database URLs, Redis connection, Qdrant endpoints, and Ollama base URLs.
- Provide a `.env.example` and environment bootstrap check script.

## Capabilities

### New Capabilities
- `project-scaffolding`: Project layout, dependency management, environment settings, and local Docker Compose services orchestration.

### Modified Capabilities
<!-- None -->

## Impact

- Establishes the core repository layout and baseline runtime dependencies.
- Services can be started with a single `docker compose up -d` command.
- Unblocks Phase 2 (Database Layer and State Models).
