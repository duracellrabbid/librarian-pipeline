"""ARQ-based implementation of the TaskDispatcher protocol."""

import inspect
from uuid import UUID

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import Settings, get_settings
from app.core.exceptions import DispatcherError

DEFAULT_INGESTION_TASK = "run_ingestion_pipeline"


def get_redis_settings(custom_settings: Settings | None = None) -> RedisSettings:
    """Construct RedisSettings from application configuration.

    Args:
        custom_settings: Optional application settings override.

    Returns:
        Configured RedisSettings instance for ARQ.
    """
    app_settings = custom_settings or get_settings()
    if app_settings.redis_url:
        return RedisSettings.from_dsn(app_settings.redis_url)
    return RedisSettings(host=app_settings.redis_host, port=app_settings.redis_port)


class ArqTaskDispatcher:
    """ARQ-backed task dispatcher enqueuing background ingestion jobs to Redis."""

    def __init__(
        self,
        pool: ArqRedis | None = None,
        redis_settings: RedisSettings | None = None,
        task_name: str = DEFAULT_INGESTION_TASK,
    ) -> None:
        """Initialize the ArqTaskDispatcher.

        Args:
            pool: Optional existing ArqRedis connection pool.
            redis_settings: Optional Redis connection settings for pool creation.
            task_name: Name of the worker task function to enqueue.
        """
        self._pool = pool
        self._redis_settings = redis_settings
        self.task_name = task_name

    async def get_pool(self, job_id: str | None = None) -> ArqRedis:
        """Get or lazily initialize the ArqRedis connection pool.

        Args:
            job_id: Optional job ID for contextual error reporting.

        Returns:
            Active ArqRedis connection pool.

        Raises:
            DispatcherError: If connecting to Redis fails.
        """
        if self._pool is not None:
            return self._pool
        try:
            settings = self._redis_settings or get_redis_settings()
            self._pool = await create_pool(settings)
            return self._pool
        except Exception as e:
            raise DispatcherError(
                f"Failed to connect to Redis queue broker: {e}",
                job_id=job_id,
                original_error=e,
            ) from e

    async def enqueue_ingestion_job(
        self,
        job_id: UUID,
        document_id: UUID,
        url: str,
    ) -> None:
        """Enqueue an ingestion job for background processing.

        Args:
            job_id: Unique identifier of the ingestion job.
            document_id: Unique identifier of the document record.
            url: Web URL to process.

        Raises:
            DispatcherError: If Redis connection fails or job cannot be enqueued.
        """
        pool = await self.get_pool(job_id=str(job_id))
        try:
            await pool.enqueue_job(
                self.task_name,
                str(job_id),
                str(document_id),
                url,
                _job_id=str(job_id),
            )
        except Exception as e:
            raise DispatcherError(
                f"Failed to enqueue ingestion job: {e}",
                job_id=str(job_id),
                original_error=e,
            ) from e

    async def close(self) -> None:
        """Close the underlying connection pool if open."""
        if self._pool is not None:
            res = self._pool.close()
            if inspect.isawaitable(res):
                await res
            self._pool = None
