## Purpose

Provides an asynchronous client to generate dense vector embeddings from text chunks using a local Ollama instance with the bge-m3 model.

## ADDED Requirements

### Requirement: Dense Vector Embedding Generation
The system SHALL generate dense vector embeddings for input text strings using Ollama's HTTP embedding endpoint with the configured `bge-m3` model.

#### Scenario: Successful single text embedding
- **WHEN** a valid text string is submitted for embedding
- **THEN** the system returns a float vector with exactly 1024 dimensions.

### Requirement: Batch Embedding Processing
The system SHALL support batch embedding of multiple document chunks, grouping texts into configurable batch sizes to optimize network and compute throughput.

#### Scenario: Batch processing multiple chunks
- **WHEN** a list of N text chunks is provided
- **THEN** the system generates N corresponding 1024-dimensional float vectors preserving input order.

### Requirement: Resilient Error Handling and Retries
The system SHALL handle transient HTTP failures, timeouts, and service unavailability by retrying with exponential backoff before raising a typed domain exception (`EmbeddingError`).

#### Scenario: Ollama service unavailable
- **WHEN** the Ollama service is unreachable or returns a 5xx error after all retry attempts
- **THEN** the system raises an `EmbeddingError` detailing the underlying connection failure without crashing the host process.

### Requirement: Vector Dimension and Format Validation
The system SHALL validate that the vector output returned by Ollama matches the expected dimension and format.

#### Scenario: Dimension mismatch detection
- **WHEN** the embedding service returns a vector whose length does not equal 1024
- **THEN** the system rejects the response and raises an `EmbeddingError` indicating a model/dimension mismatch.
