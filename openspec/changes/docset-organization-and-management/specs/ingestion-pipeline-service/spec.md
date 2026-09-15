## MODIFIED Requirements

### Requirement: Multi-Component Pipeline Orchestration
The system SHALL orchestrate content extraction (`BaseExtractor`), hybrid chunking (`BaseChunker`), vector embedding (`BaseEmbeddingClient`), and vector storage (`BaseVectorStore`) within a single unified execution flow, carrying docset context, enforcing defense-in-depth domain validation before extraction, and verifying that the target document remains active before upserting vectors into Qdrant.

#### Scenario: Successful full ingestion execution with docset tagging
- **WHEN** a valid URL from an allowed domain is processed by the pipeline service for an active document belonging to a docset
- **THEN** web content is extracted, partitioned into chunks, embedded into 1024-d vectors, and upserted into Qdrant with both `doc_id` and `docset` attached in payloads.

#### Scenario: Cancellation/deletion guard prevents ghost vector upsert
- **WHEN** a background worker completes chunking or embedding, but detects that the document was soft-deleted or its docset deleted while the job was processing
- **THEN** the pipeline halts execution immediately without upserting vectors into Qdrant, preventing orphan/ghost vectors.

#### Scenario: Pipeline worker rejection of unallowed domain
- **WHEN** a background worker receives a job with a URL not present in the allowed domains list
- **THEN** the pipeline halts execution before invoking the crawler, marks the job as `FAILED` with an error message detailing the domain violation, and does not perform web requests.
