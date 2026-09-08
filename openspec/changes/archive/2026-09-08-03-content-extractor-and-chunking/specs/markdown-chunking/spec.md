## Purpose

Defines a structure-aware hybrid Markdown chunking engine that segments documents along heading hierarchies while enforcing token/character bounds with overlap.

## ADDED Requirements

### Requirement: Hierarchical Markdown Heading Segmentation
The system SHALL segment Markdown documents by heading levels (`#`, `##`, `###`), preserving semantic section continuity.

#### Scenario: Heading boundary segmentation
- **WHEN** a Markdown document containing multiple heading levels is processed by the chunker
- **THEN** content belonging to distinct sections is partitioned into separate candidate chunks corresponding to their section hierarchy.

### Requirement: Heading Context Breadcrumb Injection
The system SHALL maintain the full hierarchical heading path and attach it as contextual metadata to each chunk.

#### Scenario: Section breadcrumb metadata
- **WHEN** a chunk is generated from a nested section (e.g. `## Early Life` under `# Biography`)
- **THEN** the chunk's metadata includes `heading_path` containing `["Biography", "Early Life"]`, and the chunk text is optionally prefixed with the contextual breadcrumb.

### Requirement: Recursive Chunk Sizing with Overlap
The system SHALL recursively split sections that exceed a configurable maximum chunk size (default: 800 tokens / 3200 characters) into smaller pieces with a configurable overlap (default: 100 tokens / 400 characters).

#### Scenario: Oversized section recursive splitting
- **WHEN** a single section's text exceeds the maximum chunk size threshold
- **THEN** the chunker recursively subdivides the section at paragraph or sentence boundaries without cutting mid-word, preserving heading metadata across all sub-chunks.

### Requirement: Standard Chunk Entity Output
The system SHALL produce a sequence of standardized `DocumentChunk` objects containing chunk index, text content, character count, token estimate, and metadata.

#### Scenario: Chunker output structure
- **WHEN** chunking completes on an extracted document
- **THEN** it returns a list of `DocumentChunk` items with monotonically increasing `chunk_index` (0, 1, 2, ...), non-empty `text`, and appropriate section metadata.
