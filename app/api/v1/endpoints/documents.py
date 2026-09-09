"""REST API endpoints for document ingestion, status tracking, checking, and deletion."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.api.schemas import (
    DeleteResponse,
    DocumentCheckResponse,
    IngestRequest,
    IngestResponse,
    JobStatusResponse,
)
from app.core.dispatcher import TaskDispatcher
from app.models import Document, IngestionJob
from app.services.repository import (
    DocumentNotFoundError,
    JobNotFoundError,
    check_active_url,
    create_document_and_job,
    soft_delete_document,
)
from app.services.vector_store.qdrant import QdrantVectorStore

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit URL for asynchronous ingestion",
)
async def ingest_document(
    payload: IngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_dispatcher)],
) -> IngestResponse:
    """Submit a URL for scraping, chunking, embedding, and vector storage."""
    url_str = str(payload.url)

    document, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url=url_str,
        title=payload.title,
    )

    await dispatcher.enqueue_ingestion_job(
        job_id=job.id,
        document_id=document.id,
        url=url_str,
    )

    return IngestResponse(
        job_id=job.id,
        doc_id=document.id,
        status=job.status,
        message="Ingestion job submitted successfully",
    )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ingestion job status and progress",
)
async def get_job_status(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobStatusResponse:
    """Retrieve real-time status and progress percentage for an ingestion job."""
    statement = select(IngestionJob).where(IngestionJob.id == job_id)
    result = await session.execute(statement)
    job = result.scalars().first()

    if job is None:
        raise JobNotFoundError(f"Ingestion job {job_id} not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress_percentage=job.progress_percentage,
        error_message=job.error_message,
    )


@router.get(
    "/check",
    response_model=DocumentCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check if a URL is actively indexed",
)
async def check_document_url(
    url: Annotated[str, Query(description="Target URL to check for active ingestion")],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentCheckResponse:
    """Verify whether a URL exists as an active document and return its latest job status."""
    doc = await check_active_url(session, url)
    if doc is None:
        return DocumentCheckResponse(exists=False, doc_id=None, status=None)

    statement = (
        select(IngestionJob)
        .where(IngestionJob.document_id == doc.id)
        .order_by(IngestionJob.created_at.desc())
    )
    result = await session.execute(statement)
    latest_job = result.scalars().first()
    latest_status = latest_job.status if latest_job is not None else None

    return DocumentCheckResponse(
        exists=True,
        doc_id=doc.id,
        status=latest_status,
    )


@router.delete(
    "/{doc_id}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-delete document and purge associated vectors",
)
async def delete_document(
    doc_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> DeleteResponse:
    """Purge vector points from Qdrant and soft-delete the document in PostgreSQL."""
    statement = select(Document).where(
        Document.id == doc_id,
        Document.deleted_at.is_(None),
    )
    result = await session.execute(statement)
    doc = result.scalars().first()

    if doc is None:
        raise DocumentNotFoundError(f"Active document {doc_id} not found")

    # Purge vectors first; if this raises VectorStoreError, DB is untouched
    await vector_store.delete_by_doc_id(str(doc_id))

    await soft_delete_document(session, doc_id)

    return DeleteResponse(
        doc_id=doc_id,
        status="deleted",
        message="Document and associated vectors successfully deleted",
    )
