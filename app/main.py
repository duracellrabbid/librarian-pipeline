"""FastAPI application entry point, lifespan configuration, middleware, and exception handlers."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import documents
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import DispatcherError, PipelineError, VectorStoreError
from app.services.repository import (
    DocumentNotFoundError,
    DuplicateActiveURLError,
    JobNotFoundError,
)
from app.services.vector_store.qdrant import QdrantVectorStore
from app.workers.dispatcher import ArqTaskDispatcher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan resources (connections and services)."""
    app.state.dispatcher = ArqTaskDispatcher()
    vector_store = QdrantVectorStore()
    try:
        await vector_store.initialize_collection()
    except Exception as exc:
        logger.warning("Failed to initialize Qdrant collection on startup: %s", exc)
    app.state.vector_store = vector_store
    try:
        yield
    finally:
        dispatcher = getattr(app.state, "dispatcher", None)
        if dispatcher is not None and hasattr(dispatcher, "close"):
            await dispatcher.close()

        vector_store = getattr(app.state, "vector_store", None)
        if vector_store is not None and hasattr(vector_store, "close"):
            await vector_store.close()

        await engine.dispose()


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain and repository exception handlers to map to semantic HTTP status codes."""

    @app.exception_handler(DuplicateActiveURLError)
    async def handle_duplicate_active_url(
        request: Request,
        exc: DuplicateActiveURLError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(JobNotFoundError)
    async def handle_job_not_found(
        request: Request,
        exc: JobNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(DocumentNotFoundError)
    async def handle_doc_not_found(
        request: Request,
        exc: DocumentNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(VectorStoreError)
    async def handle_vector_store_error(
        request: Request,
        exc: VectorStoreError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exc)},
        )

    @app.exception_handler(DispatcherError)
    async def handle_dispatcher_error(
        request: Request,
        exc: DispatcherError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)},
        )

    @app.exception_handler(PipelineError)
    async def handle_pipeline_error(
        request: Request,
        exc: PipelineError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)},
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handlers
    register_exception_handlers(application)

    # Core health check endpoint
    @application.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    # API Routing
    application.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    application.include_router(documents.router)

    return application


app = create_app()
