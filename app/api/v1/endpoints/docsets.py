"""REST API endpoints for docset management and docset-scoped document operations."""

import asyncio
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.api.schemas import (
    DeleteResponse,
    DocsetDeleteResponse,
    DocsetListItemResponse,
    DocsetListResponse,
    DocumentCheckResponse,
    DocumentListResponse,
    IngestRequest,
    IngestResponse,
)
from app.core.config import Settings, get_settings
from app.core.dispatcher import TaskDispatcher
from app.models import Document, IngestionJob
from app.services.repository import (
    DocumentNotFoundError,
    InvalidDocsetNameError,
    ReservedDocsetNameError,
    check_active_url,
    create_batch_and_jobs,
    delete_docset,
    list_active_docsets,
    list_indexed_documents,
    soft_delete_document,
)
from app.services.vector_store.qdrant import QdrantVectorStore

router = APIRouter(prefix="/docsets", tags=["docsets"])


def _clean_docset_param(docset: str, allow_reserved: bool = False) -> str:
    """Validate and normalize docset path parameter."""
    cleaned = docset.strip().lower()
    if not re.match(r"^[a-z0-9_-]{1,64}$", cleaned):
        raise InvalidDocsetNameError(f"Invalid docset name '{docset}'. Must be 1-64 characters matching ^[a-z0-9_-]+$.")
    if not allow_reserved and cleaned == "default":
        raise ReservedDocsetNameError(
            "The 'default' docset name is reserved and cannot be modified or ingested into directly."
        )
    return cleaned


@router.get(
    "",
    response_model=DocsetListResponse,
    status_code=status.HTTP_200_OK,
    summary="List active docsets",
)
async def get_docsets(
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit")] = 20,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
) -> DocsetListResponse:
    """Retrieve a paginated list of all active non-empty docsets."""
    total, docsets = await list_active_docsets(session=session, limit=limit, offset=offset)
    items = [
        DocsetListItemResponse(
            name=ds.name,
            document_count=ds.document_count,
            created_at=ds.created_at,
            updated_at=ds.updated_at,
        )
        for ds in docsets
    ]
    return DocsetListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.delete(
    "/{docset}",
    response_model=DocsetDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a docset, soft-delete member documents, and purge vectors",
)
async def remove_docset(
    docset: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> DocsetDeleteResponse:
    """Soft-delete all documents in docset, prune docset, and purge vector points."""
    normalized = _clean_docset_param(docset, allow_reserved=False)
    deleted_count = await delete_docset(session, normalized)
    await vector_store.delete_by_docset(normalized)
    return DocsetDeleteResponse(
        docset=normalized,
        status="deleted",
        deleted_document_count=deleted_count,
        message="Docset and associated vectors successfully deleted",
    )


@router.post(
    "/{docset}/documents",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit batch of URLs for asynchronous ingestion into specified docset",
)
async def ingest_into_docset(
    docset: str,
    payload: IngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_dispatcher)],
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> IngestResponse:
    """Submit document batch for ingestion scoped to docset."""
    normalized = _clean_docset_param(docset, allow_reserved=False)
    max_limit = app_settings.max_batch_ingest_size
    if len(payload.documents) > max_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Batch size {len(payload.documents)} exceeds maximum allowed limit of {max_limit}",
        )

    batch, accepted_pairs, _ = await create_batch_and_jobs(
        session=session,
        items=payload.documents,
        source_type="url",
        allowed_domains=app_settings.allowed_domains,
        docset=normalized,
    )

    if accepted_pairs:
        await asyncio.gather(
            *(
                dispatcher.enqueue_ingestion_job(
                    job_id=job.id,
                    document_id=doc.id,
                    url=doc.source_url,
                    docset=normalized,
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
    "/{docset}/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List indexed documents in a docset",
)
async def get_docset_indexed_documents(
    docset: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit")] = 20,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
    query: Annotated[str | None, Query(description="Search term in URL or title")] = None,
) -> DocumentListResponse:
    """Retrieve paginated indexed documents scoped to docset."""
    cleaned = _clean_docset_param(docset, allow_reserved=True)
    total, items = await list_indexed_documents(
        session=session,
        limit=limit,
        offset=offset,
        query=query,
        docset=cleaned,
    )
    return DocumentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get(
    "/{docset}/documents/check",
    response_model=DocumentCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check if a URL is actively indexed in a docset",
)
async def check_docset_document_url(
    docset: str,
    url: Annotated[str, Query(description="Target URL to check for active ingestion")],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentCheckResponse:
    """Verify whether a URL exists as an active document in docset and return its latest job status."""
    cleaned = _clean_docset_param(docset, allow_reserved=True)
    doc = await check_active_url(session, url, docset=cleaned)
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
    "/{docset}/documents/{doc_id}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-delete document in docset and purge associated vectors",
)
async def remove_docset_document(
    docset: str,
    doc_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
) -> DeleteResponse:
    """Purge vector points from Qdrant and soft-delete the document in docset."""
    cleaned = _clean_docset_param(docset, allow_reserved=True)

    statement = select(Document).where(
        Document.id == doc_id,
        Document.docset == cleaned,
        Document.deleted_at.is_(None),
    )
    result = await session.execute(statement)
    doc = result.scalars().first()
    if doc is None:
        raise DocumentNotFoundError(f"Active document {doc_id} not found in docset '{cleaned}'")

    await vector_store.delete_by_doc_id(str(doc_id))
    await soft_delete_document(session, doc_id, docset=cleaned)

    return DeleteResponse(
        doc_id=doc_id,
        status="deleted",
        message="Document and associated vectors successfully deleted",
    )
