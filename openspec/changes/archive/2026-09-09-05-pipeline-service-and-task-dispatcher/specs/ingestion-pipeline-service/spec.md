## Purpose

Coordinates the complete end-to-end document ingestion workflow, driving state transitions across scraping, chunking, embedding, vector storage, and metadata persistence.

## ADDED Requirements

### Requirement: Sequential Job State Progression
The system SHALL transition the background ingestion job through sequential stages (`SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`) and record progress percentages.

#### Scenario: Normal state progression
- **WHEN** an ingestion pipeline execution begins
- **THEN** the job transitions sequentially from `PENDING` to `SCRAPING`, then `CHUNKING`, `EMBEDDING`, and ultimately `INDEXED`.

### Requirement: Multi-Component Pipeline Orchestration
The system SHALL orchestrate content extraction (`BaseExtractor`), hybrid chunking (`BaseChunker`), vector embedding (`BaseEmbeddingClient`), and vector storage (`BaseVectorStore`) within a single unified execution flow.

#### Scenario: Successful full ingestion execution
- **WHEN** a valid URL is processed by the pipeline service
- **THEN** web content is extracted, partitioned into chunks with heading breadcrumbs, embedded into 1024-d vectors, and upserted into Qdrant with appropriate payloads.

### Requirement: Document Metadata Finalization
The system SHALL update the PostgreSQL `Document` record with the extracted title, content hash, and total chunk count upon successful completion.

#### Scenario: Document record updated after indexing
- **WHEN** all chunks are successfully stored in Qdrant
- **THEN** the `Document` row in PostgreSQL has its `title`, `chunk_count`, and `updated_at` fields populated, and the `IngestionJob` record is marked `INDEXED` with `finished_at` recorded.

### Requirement: Pipeline Error Capture and Graceful Failure
The system SHALL catch errors occurring at any stage of execution, set the job status to `FAILED`, record the error message, and ensure database consistency.

#### Scenario: Extractor or embedder failure during execution
- **WHEN** an exception occurs during scraping, chunking, or embedding
- **THEN** the pipeline catches the error, updates the `IngestionJob` status to `FAILED` with `error_message`, logs the failure, and terminates cleanly.
