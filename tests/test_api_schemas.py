"""Unit tests for API request and response Pydantic schemas."""

from uuid import uuid4

import pytest
from app.api.schemas import (
    ChildJobStatusResponse,
    DeleteResponse,
    DocumentCheckResponse,
    DocumentIngestItem,
    IngestRequest,
    IngestResponse,
    JobStatusResponse,
    SkippedDocumentItem,
)
from app.models.job import BatchJobStatus, JobStatus
from pydantic import ValidationError


class TestDocumentIngestItemSchema:
    """Validation and serialization tests for DocumentIngestItem."""

    def test_valid_minimal_item(self) -> None:
        url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
        item = DocumentIngestItem(url=url)
        assert str(item.url) == url
        assert item.title is None
        assert item.metadata is None

    def test_valid_full_item(self) -> None:
        url = "https://example.com/article"
        title = "Example Article"
        meta = {"author": "Alice", "tags": ["tech", "ai"]}
        item = DocumentIngestItem(url=url, title=title, metadata=meta)
        assert str(item.url) == url
        assert item.title == title
        assert item.metadata == meta

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
            DocumentIngestItem(url=invalid_url)


class TestIngestRequestSchema:
    """Validation and serialization tests for IngestRequest."""

    def test_valid_minimal_batch_request(self) -> None:
        url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
        req = IngestRequest(documents=[{"url": url}])
        assert len(req.documents) == 1
        assert str(req.documents[0].url) == url
        assert req.documents[0].title is None

    def test_valid_multi_document_request(self) -> None:
        docs = [
            {"url": "https://example.com/doc1", "title": "Doc 1"},
            {"url": "https://example.com/doc2", "metadata": {"tag": "ai"}},
        ]
        req = IngestRequest(documents=docs)
        assert len(req.documents) == 2
        assert str(req.documents[0].url) == "https://example.com/doc1"
        assert str(req.documents[1].url) == "https://example.com/doc2"

    def test_empty_documents_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            IngestRequest(documents=[])

    def test_missing_documents_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            IngestRequest()  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        url = "https://example.com/test"
        req = IngestRequest(documents=[{"url": url, "title": "Test"}])
        dumped = req.model_dump()
        assert len(dumped["documents"]) == 1
        assert str(dumped["documents"][0]["url"]) == "https://example.com/test"
        assert dumped["documents"][0]["title"] == "Test"


class TestIngestResponseSchema:
    """Validation and serialization tests for IngestResponse."""

    def test_default_values(self) -> None:
        main_job_id = uuid4()
        resp = IngestResponse(main_job_id=main_job_id)
        assert resp.main_job_id == main_job_id
        assert resp.status == BatchJobStatus.PENDING.value
        assert resp.total_submitted == 0
        assert resp.accepted_count == 0
        assert resp.skipped_count == 0
        assert "submitted" in resp.message.lower()

    def test_custom_values(self) -> None:
        main_job_id = uuid4()
        resp = IngestResponse(
            main_job_id=main_job_id,
            status="PROCESSING",
            total_submitted=5,
            accepted_count=4,
            skipped_count=1,
            message="Batch accepted",
        )
        assert resp.main_job_id == main_job_id
        assert resp.status == "PROCESSING"
        assert resp.total_submitted == 5
        assert resp.accepted_count == 4
        assert resp.skipped_count == 1
        assert resp.message == "Batch accepted"

    def test_invalid_uuid_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            IngestResponse(main_job_id="not-a-uuid")  # type: ignore[arg-type]


class TestChildJobStatusResponseSchema:
    """Validation and serialization tests for ChildJobStatusResponse."""

    def test_valid_child_job_response(self) -> None:
        doc_id = uuid4()
        job_id = uuid4()
        child = ChildJobStatusResponse(
            url="https://example.com/page",
            doc_id=doc_id,
            job_id=job_id,
            status=JobStatus.INDEXED.value,
            progress_percentage=100,
        )
        assert child.url == "https://example.com/page"
        assert child.doc_id == doc_id
        assert child.job_id == job_id
        assert child.status == "INDEXED"
        assert child.progress_percentage == 100
        assert child.error_message is None

    @pytest.mark.parametrize("invalid_progress", [-1, 101, 150])
    def test_child_progress_bounds(self, invalid_progress: int) -> None:
        with pytest.raises(ValidationError):
            ChildJobStatusResponse(
                url="https://example.com/page",
                status="SCRAPING",
                progress_percentage=invalid_progress,
            )


class TestSkippedDocumentItemSchema:
    """Validation and serialization tests for SkippedDocumentItem."""

    def test_valid_skipped_item(self) -> None:
        existing_doc = uuid4()
        item = SkippedDocumentItem(
            url="https://example.com/skipped",
            reason="already_ingested",
            existing_doc_id=existing_doc,
        )
        assert item.url == "https://example.com/skipped"
        assert item.reason == "already_ingested"
        assert item.existing_doc_id == existing_doc


class TestJobStatusResponseSchema:
    """Validation and serialization tests for JobStatusResponse."""

    def test_valid_batch_status_response(self) -> None:
        main_job_id = uuid4()
        doc_id = uuid4()
        job_id = uuid4()
        child = ChildJobStatusResponse(
            url="https://example.com/doc1",
            doc_id=doc_id,
            job_id=job_id,
            status=JobStatus.INDEXED.value,
            progress_percentage=100,
        )
        skipped = SkippedDocumentItem(
            url="https://example.com/doc2",
            reason="already_ingested",
        )
        resp = JobStatusResponse(
            main_job_id=main_job_id,
            status=BatchJobStatus.COMPLETED.value,
            overall_progress_percentage=100,
            total_jobs=2,
            completed_jobs=1,
            failed_jobs=0,
            jobs=[child],
            skipped=[skipped],
        )
        assert resp.main_job_id == main_job_id
        assert resp.status == "COMPLETED"
        assert resp.overall_progress_percentage == 100
        assert resp.total_jobs == 2
        assert resp.completed_jobs == 1
        assert resp.failed_jobs == 0
        assert len(resp.jobs) == 1
        assert len(resp.skipped) == 1

    @pytest.mark.parametrize("invalid_progress", [-1, 101, 150])
    def test_overall_progress_percentage_bounds(self, invalid_progress: int) -> None:
        with pytest.raises(ValidationError):
            JobStatusResponse(
                main_job_id=uuid4(),
                status="PROCESSING",
                overall_progress_percentage=invalid_progress,
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
