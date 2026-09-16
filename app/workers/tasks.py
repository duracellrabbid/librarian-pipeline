"""ARQ worker task runner and worker configuration settings."""

from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from loguru import logger

from app.core.config import get_settings
from app.workers.dispatcher import get_redis_settings


def coerce_uuid(val: str | UUID) -> UUID:
    """Coerce string or UUID instance to a UUID object.

    Args:
        val: Input identifier as string or UUID.

    Returns:
        UUID representation of the identifier.
    """
    return val if isinstance(val, UUID) else UUID(str(val))


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook initializing worker context.

    Args:
        ctx: Worker context dictionary.
    """
    settings = get_settings()
    ctx["settings"] = settings
    try:
        from app.services.vector_store.qdrant import QdrantVectorStore

        vector_store = QdrantVectorStore()
        await vector_store.initialize_collection()
        ctx["vector_store"] = vector_store
    except Exception as exc:
        logger.warning("Could not initialize Qdrant vector store in worker startup: {}", exc)
    logger.info("ARQ worker started for {} environment", settings.environment)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook cleaning up resources.

    Args:
        ctx: Worker context dictionary.
    """
    vector_store = ctx.get("vector_store")
    if vector_store is not None and hasattr(vector_store, "close"):
        await vector_store.close()
    logger.info("ARQ worker shutting down")


async def run_ingestion_pipeline(
    ctx: dict[str, Any],
    job_id: str | UUID,
    document_id: str | UUID,
    url: str,
    docset: str = "default",
) -> None:
    """Task function executing the document ingestion pipeline in the background.

    Args:
        ctx: ARQ worker execution context.
        job_id: Ingestion job unique identifier.
        document_id: Associated document unique identifier.
        url: Web URL to extract and process.
        docset: Target docset identifier.
    """
    parsed_job_id = coerce_uuid(job_id)
    parsed_doc_id = coerce_uuid(document_id)

    with logger.contextualize(job_id=str(parsed_job_id), document_id=str(parsed_doc_id)):
        service = ctx.get("pipeline_service")
        if service is None:
            try:
                from app.services.pipeline import IngestionPipelineService

                vector_store = ctx.get("vector_store")
                service = IngestionPipelineService(vector_store=vector_store)
            except (ImportError, AttributeError):
                logger.warning(
                    "IngestionPipelineService not available; skipping pipeline run for job {}",
                    parsed_job_id,
                )
                return

        await service.run(
            job_id=parsed_job_id,
            document_id=parsed_doc_id,
            url=url,
            docset=docset,
        )


class WorkerSettings:
    """ARQ worker process configuration."""

    functions = [run_ingestion_pipeline]
    redis_settings: RedisSettings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs: int = 10
    job_timeout: int = get_settings().arq_job_timeout
