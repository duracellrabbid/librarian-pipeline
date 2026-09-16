"""REST API endpoints for document ingestion, status tracking, checking, and deletion."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.api.schemas import (
    DeleteResponse,
    DocumentCheckResponse,
    DocumentListResponse,
    IngestRequest,
    IngestResponse,
    JobStatusResponse,
)
from app.core.config import Settings, get_settings
from app.core.dispatcher import TaskDispatcher
from app.models import Document, IngestionJob
from app.services.repository import (
    DocumentNotFoundError,
    check_active_url,
    create_batch_and_jobs,
    get_batch_job_status,
    list_indexed_documents,
    soft_delete_document,
)
from app.services.vector_store.qdrant import QdrantVectorStore

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit batch of URLs for asynchronous ingestion",
)
async def ingest_document(
    payload: IngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> IngestResponse:
    """Submit a batch of URLs for scraping, chunking, embedding, and vector storage."""
    app_settings = settings or get_settings()
    max_limit = app_settings.max_batch_ingest_size
    if len(payload.documents) > max_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Batch size {len(payload.documents)} exceeds maximum allowed limit of {max_limit}"),
        )

    batch, accepted_pairs, _ = await create_batch_and_jobs(
        session=session,
        items=payload.documents,
        source_type="url",
        allowed_domains=app_settings.allowed_domains,
    )

    if accepted_pairs:
        await asyncio.gather(
            *(
                dispatcher.enqueue_ingestion_job(
                    job_id=job.id,
                    document_id=doc.id,
                    url=doc.source_url,
                    docset=doc.docset,
                )
                for doc, job in accepted_pairs
            )
        )

    return IngestResponse(
        main_job_id=batch.id,
        status=batch.status,
        total_submitted=batch.total_count,
        accepted_count=batch.accepted_count,
        skipped_count=batch.skipped_count,
        message="Ingestion batch submitted successfully",
    )


@router.get(
    "/status/{main_job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get batch ingestion job status and progress",
)
async def get_job_status(
    main_job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobStatusResponse:
    """Retrieve aggregate status and progress for a batch ingestion job."""
    return await get_batch_job_status(session=session, batch_id=main_job_id)


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List actively indexed documents",
)
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of documents to return per page",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of documents to skip",
        ),
    ] = 0,
    query: Annotated[
        str | None,
        Query(
            description="Optional case-insensitive substring search for URL or title",
        ),
    ] = None,
) -> DocumentListResponse:
    """Retrieve a paginated list of documents currently indexed in vector storage."""
    total, items = await list_indexed_documents(
        session=session,
        limit=limit,
        offset=offset,
        query=query,
    )
    return DocumentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
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

    statement = select(IngestionJob).where(IngestionJob.document_id == doc.id).order_by(IngestionJob.created_at.desc())
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
