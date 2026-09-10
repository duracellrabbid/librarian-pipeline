"""Ingestion pipeline orchestration service."""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory
from app.models.job import JobStatus
from app.services.chunkers.base import BaseChunker, DocumentChunk
from app.services.embeddings.base import BaseEmbeddingClient
from app.services.extractors.base import BaseExtractor, ExtractedDocument
from app.services.repository import update_document_metadata, update_job_status
from app.services.vector_store.base import BaseVectorStore

logger = logging.getLogger(__name__)


class IngestionPipelineService:
    """Orchestrates end-to-end document ingestion from extraction to vector indexing."""

    def __init__(
        self,
        extractor: BaseExtractor | None = None,
        chunker: BaseChunker | None = None,
        embedding_client: BaseEmbeddingClient | None = None,
        vector_store: BaseVectorStore | None = None,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the ingestion pipeline service with injected dependencies.

        Args:
            extractor: Web or file content extractor instance.
            chunker: Markdown or text chunking strategy instance.
            embedding_client: Dense embedding client instance.
            vector_store: Vector store adapter instance.
            session_factory: Factory returning an async database session.
        """
        self.extractor = extractor or self._default_extractor()
        self.chunker = chunker or self._default_chunker()
        self.embedding_client = embedding_client or self._default_embedding_client()
        self.vector_store = vector_store or self._default_vector_store()
        self.session_factory = session_factory or async_session_factory

    @staticmethod
    def _default_extractor() -> BaseExtractor:
        """Lazily initialize the default Crawl4AIExtractor."""
        from app.services.extractors.web import Crawl4AIExtractor

        return Crawl4AIExtractor()

    @staticmethod
    def _default_chunker() -> BaseChunker:
        """Lazily initialize the default HybridMarkdownChunker."""
        from app.services.chunkers.hybrid import HybridMarkdownChunker

        return HybridMarkdownChunker()

    @staticmethod
    def _default_embedding_client() -> BaseEmbeddingClient:
        """Lazily initialize the default OllamaEmbeddingClient."""
        from app.services.embeddings.ollama import OllamaEmbeddingClient

        return OllamaEmbeddingClient()

    @staticmethod
    def _default_vector_store() -> BaseVectorStore:
        """Lazily initialize the default QdrantVectorStore."""
        from app.services.vector_store.qdrant import QdrantVectorStore

        return QdrantVectorStore()

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """Obtain an async database session from the session factory."""
        session_obj = self.session_factory()
        if hasattr(session_obj, "__aenter__"):
            async with session_obj as session:
                yield session
        else:
            yield session_obj

    async def _update_job(
        self,
        job_id: UUID,
        status: JobStatus,
        progress: int | None,
        error_message: str | None = None,
    ) -> None:
        """Update job status and progress in a scoped session."""
        async with self._get_session() as session:
            await update_job_status(
                session=session,
                job_id=job_id,
                status=status,
                progress_percentage=progress,
                error_message=error_message,
            )

    async def _finalize_document(
        self,
        document_id: UUID,
        title: str,
        chunk_count: int,
        content_hash: str,
    ) -> None:
        """Update document metadata in a scoped session."""
        async with self._get_session() as session:
            await update_document_metadata(
                session=session,
                document_id=document_id,
                title=title,
                chunk_count=chunk_count,
                content_hash=content_hash,
            )

    async def _extract_content(self, job_id: UUID, url: str) -> ExtractedDocument:
        """Transition job to SCRAPING (20%) and extract document content."""
        await self._update_job(job_id, JobStatus.SCRAPING, 20)
        return await self.extractor.extract(url)

    def _chunk_content(self, extracted: ExtractedDocument) -> list[DocumentChunk]:
        """Split extracted document content into structured chunks."""
        return self.chunker.chunk(extracted)

    async def _embed_and_index_chunks(
        self,
        job_id: UUID,
        document_id: UUID,
        url: str,
        chunks: list[DocumentChunk],
    ) -> None:
        """Transition job to EMBEDDING (70%), generate vectors, and upsert to vector store."""
        await self._update_job(job_id, JobStatus.EMBEDDING, 70)
        if not chunks:
            return

        texts = [chunk.text for chunk in chunks]
        vectors = await self.embedding_client.embed_batch(texts)
        await self.vector_store.initialize_collection()
        await self.vector_store.upsert_chunks(
            doc_id=str(document_id),
            chunks=chunks,
            vectors=vectors,
            source_url=url,
        )

    async def _execute_pipeline(
        self,
        job_id: UUID,
        document_id: UUID,
        url: str,
    ) -> None:
        """Execute the sequential stages of the ingestion pipeline."""
        extracted = await self._extract_content(job_id, url)

        await self._update_job(job_id, JobStatus.CHUNKING, 40)
        chunks = self._chunk_content(extracted)

        await self._embed_and_index_chunks(job_id, document_id, url, chunks)

        content_hash = hashlib.sha256(extracted.content.encode("utf-8")).hexdigest()
        await self._finalize_document(
            document_id=document_id,
            title=extracted.title,
            chunk_count=len(chunks),
            content_hash=content_hash,
        )

        await self._update_job(job_id, JobStatus.INDEXED, 100)

    async def _handle_failure(self, job_id: UUID, exc: Exception) -> None:
        """Set job state to FAILED with error message."""
        error_msg = f"{type(exc).__name__}: {exc}"
        try:
            await self._update_job(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress=None,
                error_message=error_msg,
            )
        except Exception as db_exc:
            logger.exception(
                "Failed to update FAILED status for job %s: %s",
                job_id,
                db_exc,
            )

    async def run(
        self,
        job_id: UUID,
        document_id: UUID,
        url: str,
    ) -> None:
        """Execute the end-to-end ingestion pipeline with robust error capture.

        Args:
            job_id: Unique identifier of the ingestion job.
            document_id: Unique identifier of the associated document.
            url: Target web URL to extract, chunk, embed, and store.
        """
        try:
            await self._execute_pipeline(job_id, document_id, url)
        except asyncio.CancelledError:
            logger.warning("Ingestion pipeline cancelled or timed out for job %s", job_id)
            await asyncio.shield(
                self._handle_failure(
                    job_id,
                    TimeoutError("Job timed out or was cancelled during execution"),
                )
            )
            raise
        except Exception as exc:
            logger.exception("Ingestion pipeline failed for job %s: %s", job_id, exc)
            await self._handle_failure(job_id, exc)
