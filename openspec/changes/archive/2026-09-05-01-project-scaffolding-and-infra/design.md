## Context

See `proposal.md` for motivation. The project is an empty workspace that needs to become a Python 3.11+ application capable of connecting to PostgreSQL, Redis, Qdrant, and Ollama. The goal of this phase is strictly to lay out the repository, configure containerized services, and establish validated settings.

## Goals / Non-Goals

**Goals:**
- Provide a clean `pyproject.toml` with pinned dependency groups (core, dev/test).
- Set up `docker-compose.yml` defining PostgreSQL 16, Redis 7, Qdrant (v1.9+), and Ollama with named volumes for data persistence.
- Implement `app/core/config.py` using `pydantic-settings` to provide typed, validated settings loaded from `.env`.
- Establish project directory structure under `app/`.

**Non-Goals:**
- Creating database tables or running migrations (deferred to Phase 2).
- Implementing scrapers, chunkers, or vector logic (deferred to Phases 3-5).
- Exposing REST API endpoints (deferred to Phase 6).

## Decisions

### Decision: Pydantic-Settings for Configuration
- **Rationale**: Provides automatic environment variable parsing, type coercion, and immediate fail-fast validation on missing required parameters (e.g. database connection strings).
- **Alternatives considered**: `python-dotenv` with `os.getenv` (lacks type safety and validation).

### Decision: Docker Compose for Local Services
- **Rationale**: Isolates PostgreSQL, Redis, Qdrant, and Ollama without requiring developers or the host to install separate native services.
- **Alternatives considered**: Local native installations (inconvenient across OS environments, harder to reset state).

### Decision: Directory Structure Layout
- **Pattern**:
  ```
  app/
  ├── core/         # Config, logging, common base types
  ├── models/       # Database & domain models
  ├── services/     # Ingestion pipeline, extractors, chunkers
  ├── workers/      # ARQ worker tasks & dispatchers
  └── api/          # FastAPI routers and endpoints
  tests/            # Unit and integration tests
  ```

## Risks / Trade-offs

- **[Risk] Docker Resource Contention**: Running PostgreSQL, Redis, Qdrant, and Ollama concurrently on a single machine with limited RAM.
  - *Mitigation*: Set sensible memory reservations and volume mounts in `docker-compose.yml`; document recommended host specs.
- **[Risk] Ollama Model Pull Delay**: Ollama container starts without `bge-m3` downloaded.
  - *Mitigation*: Document and provide a setup helper script (`scripts/bootstrap_env.py` or shell script) that runs `ollama pull bge-m3`.
