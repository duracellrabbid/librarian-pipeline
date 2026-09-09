"""Unit tests for API request and response Pydantic schemas."""

from uuid import uuid4

import pytest
from app.api.schemas import (
    DeleteResponse,
    DocumentCheckResponse,
    IngestRequest,
    IngestResponse,
    JobStatusResponse,
)
from app.models.job import JobStatus
from pydantic import ValidationError


class TestIngestRequestSchema:
    """Validation and serialization tests for IngestRequest."""

    def test_valid_minimal_request(self) -> None:
        url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
        req = IngestRequest(url=url)
        assert str(req.url) == url
        assert req.title is None
        assert req.metadata is None

    def test_valid_full_request(self) -> None:
        url = "https://example.com/article"
        title = "Example Article"
        meta = {"author": "Alice", "tags": ["tech", "ai"]}
        req = IngestRequest(url=url, title=title, metadata=meta)
        assert str(req.url) == url
        assert req.title == title
        assert req.metadata == meta

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "",
            "not-a-url",
            "ftp://example.com/file.txt",
            "file:///path/to/file",
            "mailto:user@example.com",
            "javascript:alert(1)",
        ],
    )
    def test_invalid_url_raises_validation_error(self, invalid_url: str) -> None:
        with pytest.raises(ValidationError):
            IngestRequest(url=invalid_url)

    def test_missing_url_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            IngestRequest()  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        url = "https://example.com/test"
        req = IngestRequest(url=url, title="Test")
        dumped = req.model_dump()
        assert str(dumped["url"]) == url
        assert dumped["title"] == "Test"
        assert dumped["metadata"] is None


class TestIngestResponseSchema:
    """Validation and serialization tests for IngestResponse."""

    def test_default_values(self) -> None:
        job_id = uuid4()
        doc_id = uuid4()
        resp = IngestResponse(job_id=job_id, doc_id=doc_id)
        assert resp.job_id == job_id
        assert resp.doc_id == doc_id
        assert resp.status == JobStatus.PENDING.value
        assert "submitted" in resp.message.lower()

    def test_custom_values(self) -> None:
        job_id = uuid4()
        doc_id = uuid4()
        resp = IngestResponse(
            job_id=job_id,
            doc_id=doc_id,
            status="QUEUED",
            message="Queued for ingestion",
        )
        assert resp.job_id == job_id
        assert resp.doc_id == doc_id
        assert resp.status == "QUEUED"
        assert resp.message == "Queued for ingestion"

    def test_invalid_uuid_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            IngestResponse(job_id="not-a-uuid", doc_id=uuid4())  # type: ignore[arg-type]


class TestJobStatusResponseSchema:
    """Validation and serialization tests for JobStatusResponse."""

    def test_valid_status_response(self) -> None:
        job_id = uuid4()
        resp = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.SCRAPING.value,
            progress_percentage=25,
            error_message=None,
        )
        assert resp.job_id == job_id
        assert resp.status == "SCRAPING"
        assert resp.progress_percentage == 25
        assert resp.error_message is None

    def test_failed_status_with_error(self) -> None:
        job_id = uuid4()
        resp = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.FAILED.value,
            progress_percentage=40,
            error_message="HTTP 404 Not Found",
        )
        assert resp.status == "FAILED"
        assert resp.error_message == "HTTP 404 Not Found"

    @pytest.mark.parametrize("invalid_progress", [-1, 101, 150])
    def test_progress_percentage_bounds(self, invalid_progress: int) -> None:
        with pytest.raises(ValidationError):
            JobStatusResponse(
                job_id=uuid4(),
                status="SCRAPING",
                progress_percentage=invalid_progress,
            )


class TestDocumentCheckResponseSchema:
    """Validation and serialization tests for DocumentCheckResponse."""

    def test_active_document_exists(self) -> None:
        doc_id = uuid4()
        resp = DocumentCheckResponse(
            exists=True,
            doc_id=doc_id,
            status=JobStatus.INDEXED.value,
        )
        assert resp.exists is True
        assert resp.doc_id == doc_id
        assert resp.status == "INDEXED"

    def test_non_existent_document(self) -> None:
        resp = DocumentCheckResponse(exists=False)
        assert resp.exists is False
        assert resp.doc_id is None
        assert resp.status is None

    def test_missing_exists_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCheckResponse()  # type: ignore[call-arg]


class TestDeleteResponseSchema:
    """Validation and serialization tests for DeleteResponse."""

    def test_default_values(self) -> None:
        doc_id = uuid4()
        resp = DeleteResponse(doc_id=doc_id)
        assert resp.doc_id == doc_id
        assert resp.status == "deleted"
        assert "deleted" in resp.message.lower()

    def test_custom_values(self) -> None:
        doc_id = uuid4()
        resp = DeleteResponse(
            doc_id=doc_id,
            status="purged",
            message="Purged completely",
        )
        assert resp.doc_id == doc_id
        assert resp.status == "purged"
        assert resp.message == "Purged completely"
