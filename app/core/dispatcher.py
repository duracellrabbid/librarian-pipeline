"""Abstract task dispatcher protocol definition."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class TaskDispatcher(Protocol):
    """Abstract protocol defining the background task dispatcher interface."""

    async def enqueue_ingestion_job(
        self,
        job_id: UUID,
        document_id: UUID,
        url: str,
    ) -> None:
        """Enqueue an ingestion job for background processing.

        Args:
            job_id: Unique identifier of the ingestion job.
            document_id: Unique identifier of the associated document.
            url: Web URL to be scraped and indexed.

        Raises:
            DispatcherError: If the queue broker is unreachable or enqueueing fails.
        """
        ...
