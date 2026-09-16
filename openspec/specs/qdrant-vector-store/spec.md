# qdrant-vector-store Specification

## Purpose
Provides vector database storage, indexing, and cascade deletion mechanisms using Qdrant for dense document chunks.
## Requirements
### Requirement: Idempotent Collection Initialization
The system SHALL verify and idempotently create the target Qdrant vector collection (`knowledge_base`) configured with Cosine distance and 1024 vector dimensions upon startup or first access, ensuring keyword payload indexes exist on both `doc_id` and `docset`.

#### Scenario: Collection auto-creation when missing
- **WHEN** the vector store client initializes and the target collection does not exist in Qdrant
- **THEN** the collection is created with 1024-dimensional dense vector support and Cosine distance metric, and keyword indexes are established for `doc_id` and `docset`.

#### Scenario: Collection already exists
- **WHEN** the vector store client initializes and the target collection already exists
- **THEN** initialization verifies and creates missing payload indexes for `doc_id` and `docset` without modifying or overwriting existing collection contents.

### Requirement: Document ID Payload Indexing
The system SHALL ensure a keyword payload index exists on the `doc_id` field within the collection to facilitate high-speed filtered queries and bulk deletions.

#### Scenario: Keyword payload index creation
- **WHEN** the collection is initialized or verified
- **THEN** a keyword schema index on `doc_id` is established if not already present.

### Requirement: Chunk Vector Upsert with Payload Metadata
The system SHALL upsert document chunks and their associated vector embeddings into Qdrant, attaching rich metadata payloads including `doc_id`, `docset`, `chunk_index`, `text`, `source_url`, and `heading_path`.

#### Scenario: Successful chunk vector batch upsert
- **WHEN** a list of chunks, their corresponding embeddings, document ID, and docset identifier are provided
- **THEN** points are stored in Qdrant with deterministic UUIDs and complete queryable payload fields including `docset`.

### Requirement: Filtered Cascade Deletion by Document ID
The system SHALL delete all vector points associated with a specified `doc_id` using a payload filter, without requiring individual point IDs.

#### Scenario: Document deletion purging all associated chunk vectors
- **WHEN** a deletion is requested for a specific `doc_id`
- **THEN** all vector points in Qdrant with matching `doc_id` in their payload are deleted, leaving points from other documents untouched.

### Requirement: Similarity Search by Vector
The system SHALL provide vector similarity search returning top-k nearest chunks with similarity scores and payloads, optionally filtered by `docset`, `doc_id`, or other metadata fields.

#### Scenario: Nearest neighbor search
- **WHEN** a 1024-dimensional query vector is submitted with a `docset` filter and limit K
- **THEN** only chunk vectors matching the specified `docset` are evaluated, returning the top K results in descending score order.

#### Scenario: Global nearest neighbor search without docset filter
- **WHEN** a query vector is submitted without a `docset` filter
- **THEN** chunks across all docsets are evaluated and returned.

### Requirement: Filtered Cascade Deletion by Docset
The system SHALL delete all vector points associated with a specified `docset` using a Qdrant payload filter without requiring individual point IDs or document IDs.

#### Scenario: Bulk purging all chunk vectors for a docset
- **WHEN** a deletion is requested for a specific `docset`
- **THEN** all vector points in Qdrant with matching `docset` in their payload are deleted in a single call, leaving points from other docsets untouched.

