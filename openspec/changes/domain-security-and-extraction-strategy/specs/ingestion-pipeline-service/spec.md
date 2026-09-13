## MODIFIED Requirements

### Requirement: Multi-Component Pipeline Orchestration
The system SHALL orchestrate content extraction (`BaseExtractor`), hybrid chunking (`BaseChunker`), vector embedding (`BaseEmbeddingClient`), and vector storage (`BaseVectorStore`) within a single unified execution flow, enforcing defense-in-depth domain validation before extraction.

#### Scenario: Successful full ingestion execution
- **WHEN** a valid URL from an allowed domain is processed by the pipeline service
- **THEN** web content is extracted via the matched domain strategy, partitioned into chunks with heading breadcrumbs, embedded into 1024-d vectors, and upserted into Qdrant with appropriate payloads.

#### Scenario: Pipeline worker rejection of unallowed domain
- **WHEN** a background worker receives a job with a URL not present in the allowed domains list
- **THEN** the pipeline halts execution before invoking the crawler, marks the job as `FAILED` with an error message detailing the domain violation, and does not perform web requests.
