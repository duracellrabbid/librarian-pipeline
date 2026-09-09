"""Domain exceptions for the RAG ingestion pipeline."""


class PipelineError(Exception):
    """Base exception for all pipeline-related errors."""


class ExtractionError(PipelineError):
    """Domain exception raised when document extraction fails."""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class EmbeddingError(PipelineError):
    """Domain exception raised when vector embedding fails."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.status_code = status_code


class VectorStoreError(PipelineError):
    """Domain exception raised when vector storage operation fails."""

    def __init__(
        self,
        message: str,
        *,
        collection_name: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.collection_name = collection_name
        self.status_code = status_code


class DispatcherError(PipelineError):
    """Domain exception raised when background task dispatching fails."""

    def __init__(
        self,
        message: str,
        *,
        job_id: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.job_id = job_id
        self.original_error = original_error
