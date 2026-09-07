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
