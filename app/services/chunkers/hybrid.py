"""Hybrid structure-aware Markdown chunker implementation."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.chunkers.base import BaseChunker, DocumentChunk
from app.services.extractors.base import ExtractedDocument

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_CODE_FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")
DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]


@dataclass
class MarkdownSection:
    """Logical section within a Markdown document bounded by heading boundaries."""

    level: int
    title: str
    heading_path: list[str] = field(default_factory=list)
    content: str = ""


def parse_markdown_sections(markdown: str) -> list[MarkdownSection]:
    """Parse Markdown content into structured sections tracking breadcrumb hierarchies.

    Protects fenced code blocks from having inner '#' comments misidentified as headings.

    Args:
        markdown: Raw or cleaned Markdown string.

    Returns:
        List of MarkdownSection objects with populated heading_path hierarchies.
    """
    lines = markdown.splitlines()
    sections: list[MarkdownSection] = []

    current_level = 0
    current_title = ""
    heading_stack: list[tuple[int, str]] = []
    current_content_lines: list[str] = []

    in_code_block = False
    code_fence_marker = ""

    def finalize_current_section() -> None:
        nonlocal current_content_lines
        content = "\n".join(current_content_lines).strip()
        if content or current_title:
            current_path = [title for (_, title) in heading_stack]
            sections.append(
                MarkdownSection(
                    level=current_level,
                    title=current_title,
                    heading_path=current_path,
                    content=content,
                )
            )
        current_content_lines = []

    for line in lines:
        stripped = line.strip()

        # Check for fenced code block delimiters
        fence_match = _CODE_FENCE_PATTERN.match(stripped)
        if fence_match:
            fence = fence_match.group(1)
            if not in_code_block:
                in_code_block = True
                code_fence_marker = fence[:3]
            elif stripped.startswith(code_fence_marker):
                in_code_block = False
                code_fence_marker = ""
            current_content_lines.append(line)
            continue

        if in_code_block:
            current_content_lines.append(line)
            continue

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            finalize_current_section()
            hashes, raw_title = heading_match.groups()
            level = len(hashes)
            title = raw_title.strip()

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            heading_stack.append((level, title))
            current_level = level
            current_title = title
        else:
            current_content_lines.append(line)

    finalize_current_section()

    if not sections and markdown.strip():
        sections.append(
            MarkdownSection(
                level=0,
                title="",
                heading_path=[],
                content=markdown.strip(),
            )
        )

    return sections


def recursive_split_text(
    text: str,
    *,
    max_chunk_size: int = 3200,
    chunk_overlap: int = 400,
    separators: list[str] | None = None,
) -> list[str]:
    """Recursively split oversized text along natural boundaries with overlap.

    Args:
        text: Input string to split.
        max_chunk_size: Maximum character count per chunk.
        chunk_overlap: Target character overlap between consecutive chunks.
        separators: Hierarchical list of split separators.

    Returns:
        List of text chunks, each constrained to max_chunk_size.
    """
    if len(text) <= max_chunk_size:
        return [text] if text.strip() else []

    active_separators = separators if separators is not None else DEFAULT_SEPARATORS

    # Select the first applicable separator that exists in text
    chosen_separator = ""
    separator_index = len(active_separators)
    for i, sep in enumerate(active_separators):
        if sep == "":
            chosen_separator = ""
            separator_index = i
            break
        if sep in text:
            chosen_separator = sep
            separator_index = i
            break

    # Fallback to character slicing when no delimiter or at terminal separator
    if chosen_separator == "":
        step = max(1, max_chunk_size - chunk_overlap)
        return [text[i : i + max_chunk_size] for i in range(0, len(text), step)]

    # Split text by chosen separator
    splits = text.split(chosen_separator)
    next_separators = active_separators[separator_index + 1 :]

    # Recursively break down any individual pieces that exceed max_chunk_size
    refined_pieces: list[str] = []
    for part in splits:
        if len(part) > max_chunk_size:
            refined_pieces.extend(
                recursive_split_text(
                    part,
                    max_chunk_size=max_chunk_size,
                    chunk_overlap=chunk_overlap,
                    separators=next_separators,
                )
            )
        elif part:
            refined_pieces.append(part)

    # Greedily merge pieces up to max_chunk_size with overlap
    chunks: list[str] = []
    accumulator: list[str] = []
    current_length = 0

    for piece in refined_pieces:
        added_len = len(chosen_separator) + len(piece) if accumulator else len(piece)
        if current_length + added_len <= max_chunk_size:
            accumulator.append(piece)
            current_length += added_len
        else:
            if accumulator:
                merged = chosen_separator.join(accumulator).strip()
                if merged:
                    chunks.append(merged)

            # Build overlap from trailing pieces of the emitted chunk
            overlap_pieces: list[str] = []
            overlap_len = 0
            if chunk_overlap > 0 and accumulator:
                for past_piece in reversed(accumulator):
                    candidate_len = (
                        overlap_len + len(chosen_separator) + len(past_piece)
                        if overlap_pieces
                        else len(past_piece)
                    )
                    if candidate_len <= chunk_overlap:
                        overlap_pieces.insert(0, past_piece)
                        overlap_len = candidate_len
                    else:
                        break

            # Ensure adding the new piece won't exceed max_chunk_size with overlap
            while overlap_pieces and (
                len(chosen_separator.join(overlap_pieces)) + len(chosen_separator) + len(piece)
                > max_chunk_size
            ):
                overlap_pieces.pop(0)

            accumulator = [*overlap_pieces, piece]
            current_length = len(chosen_separator.join(accumulator))

    if accumulator:
        merged = chosen_separator.join(accumulator).strip()
        if merged:
            chunks.append(merged)

    return chunks


class HybridMarkdownChunker(BaseChunker):
    """Context-aware Markdown chunker with heading breadcrumbs and recursive splitting."""

    def __init__(
        self,
        *,
        max_chunk_size: int = 3200,
        chunk_overlap: int = 400,
        inject_breadcrumbs: bool = True,
        breadcrumb_prefix: str = "[Context: {breadcrumb}]\n\n",
    ) -> None:
        """Initialize HybridMarkdownChunker with configurable sizing and formatting.

        Args:
            max_chunk_size: Maximum character threshold per chunk (default 3200 ~= 800 tokens).
            chunk_overlap: Overlap characters between recursively split chunks (default 400).
            inject_breadcrumbs: If True, prepends heading path context to chunk text.
            breadcrumb_prefix: Template for prepending breadcrumbs.
        """
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= max_chunk_size:
            raise ValueError("chunk_overlap must be non-negative and less than max_chunk_size")

        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.inject_breadcrumbs = inject_breadcrumbs
        self.breadcrumb_prefix = breadcrumb_prefix

    def chunk(
        self,
        document: ExtractedDocument | str,
        metadata: dict[str, Any] | None = None,
    ) -> list[DocumentChunk]:
        """Chunk a document or raw Markdown string into structure-aware DocumentChunks.

        Args:
            document: ExtractedDocument instance or Markdown text string.
            metadata: Optional additional metadata dictionary to merge into chunks.

        Returns:
            List of standardized DocumentChunk entities.
        """
        if isinstance(document, ExtractedDocument):
            raw_content = document.content
            base_meta: dict[str, Any] = {
                "source_url": document.source_url,
                "document_title": document.title,
                **document.metadata,
            }
        else:
            raw_content = str(document)
            base_meta = {}

        if metadata:
            base_meta.update(metadata)

        if not raw_content or not raw_content.strip():
            return []

        sections = parse_markdown_sections(raw_content)
        chunks: list[DocumentChunk] = []

        for section in sections:
            if not section.content.strip():
                continue

            breadcrumb = " > ".join(section.heading_path) if section.heading_path else ""
            should_inject = self.inject_breadcrumbs and bool(breadcrumb)
            prefix = self.breadcrumb_prefix.format(breadcrumb=breadcrumb) if should_inject else ""

            candidate_text = f"{prefix}{section.content.strip()}"

            section_meta: dict[str, Any] = {
                **base_meta,
                "heading_path": list(section.heading_path),
                "breadcrumb": breadcrumb,
            }

            if len(candidate_text) <= self.max_chunk_size:
                chunks.append(
                    DocumentChunk(
                        chunk_index=len(chunks),
                        text=candidate_text,
                        metadata=section_meta,
                    )
                )
            else:
                # Oversized section requires recursive splitting
                effective_max = max(50, self.max_chunk_size - len(prefix))
                effective_overlap = min(self.chunk_overlap, effective_max // 2)

                sub_splits = recursive_split_text(
                    section.content.strip(),
                    max_chunk_size=effective_max,
                    chunk_overlap=effective_overlap,
                )

                for sub in sub_splits:
                    sub_text = f"{prefix}{sub}" if prefix else sub
                    chunks.append(
                        DocumentChunk(
                            chunk_index=len(chunks),
                            text=sub_text,
                            metadata=section_meta,
                        )
                    )

        return chunks
