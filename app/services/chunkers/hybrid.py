"""Hybrid structure-aware Markdown chunker implementation."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.chunkers.base import BaseChunker, DocumentChunk
from app.services.extractors.base import ExtractedDocument

_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(\S.*)$")
_CODE_FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")
DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]


@dataclass
class MarkdownSection:
    """Logical section within a Markdown document bounded by heading boundaries."""

    level: int
    title: str
    heading_path: list[str] = field(default_factory=list)
    content: str = ""


class _MarkdownSectionParser:
    """Helper state tracker for Markdown section parsing."""

    def __init__(self) -> None:
        self.sections: list[MarkdownSection] = []
        self.current_level = 0
        self.current_title = ""
        self.heading_stack: list[tuple[int, str]] = []
        self.current_content_lines: list[str] = []
        self.in_code_block = False
        self.code_fence_marker = ""

    def process_line(self, line: str) -> None:
        """Process a single line of Markdown, tracking code fences and heading hierarchy."""
        if self._handle_code_block(line):
            return

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            self._handle_heading(heading_match)
        else:
            self.current_content_lines.append(line)

    def _handle_code_block(self, line: str) -> bool:
        """Track entry and exit of fenced code blocks to protect inner text."""
        stripped = line.strip()
        fence_match = _CODE_FENCE_PATTERN.match(stripped)
        if fence_match:
            self._toggle_fence(fence_match.group(1), stripped)
            self.current_content_lines.append(line)
            return True
        if self.in_code_block:
            self.current_content_lines.append(line)
            return True
        return False

    def _toggle_fence(self, fence: str, stripped: str) -> None:
        """Toggle in_code_block state based on matching fence delimiters."""
        if not self.in_code_block:
            self.in_code_block = True
            self.code_fence_marker = fence[:3]
        elif stripped.startswith(self.code_fence_marker):
            self.in_code_block = False
            self.code_fence_marker = ""

    def _handle_heading(self, match: re.Match[str]) -> None:
        """Finalize prior section and push new heading onto the hierarchy stack."""
        self.finalize_section()
        hashes, raw_title = match.groups()
        level = len(hashes)
        title = raw_title.strip()

        while self.heading_stack and self.heading_stack[-1][0] >= level:
            self.heading_stack.pop()

        self.heading_stack.append((level, title))
        self.current_level = level
        self.current_title = title

    def finalize_section(self) -> None:
        """Flush accumulated content into a new MarkdownSection."""
        content = "\n".join(self.current_content_lines).strip()
        if content or self.current_title:
            current_path = [title for (_, title) in self.heading_stack]
            self.sections.append(
                MarkdownSection(
                    level=self.current_level,
                    title=self.current_title,
                    heading_path=current_path,
                    content=content,
                )
            )
        self.current_content_lines = []


def parse_markdown_sections(markdown: str) -> list[MarkdownSection]:
    """Parse Markdown content into structured sections tracking breadcrumb hierarchies.

    Protects fenced code blocks from having inner '#' comments misidentified as headings.

    Args:
        markdown: Raw or cleaned Markdown string.

    Returns:
        List of MarkdownSection objects with populated heading_path hierarchies.
    """
    parser = _MarkdownSectionParser()
    for line in markdown.splitlines():
        parser.process_line(line)
    parser.finalize_section()
    return parser.sections


def _choose_separator(text: str, separators: list[str]) -> tuple[str, int]:
    """Identify the first applicable separator occurring within text."""
    for i, sep in enumerate(separators):
        if sep == "" or sep in text:
            return sep, i
    return "", len(separators)


def _refine_splits(
    splits: list[str],
    separator_index: int,
    active_separators: list[str],
    max_chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Recursively split pieces that exceed max_chunk_size using subsequent separators."""
    next_separators = active_separators[separator_index + 1 :]
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
    return refined_pieces


def _compute_overlap(
    accumulator: list[str],
    separator: str,
    chunk_overlap: int,
    new_piece: str,
    max_chunk_size: int,
) -> list[str]:
    """Extract trailing pieces from accumulator within the overlap budget for the next chunk."""
    if chunk_overlap <= 0 or not accumulator:
        return []

    overlap_pieces: list[str] = []
    overlap_len = 0
    for past_piece in reversed(accumulator):
        candidate_len = (
            overlap_len + len(separator) + len(past_piece) if overlap_pieces else len(past_piece)
        )
        if candidate_len > chunk_overlap:
            break
        overlap_pieces.insert(0, past_piece)
        overlap_len = candidate_len

    while overlap_pieces and (
        len(separator.join(overlap_pieces)) + len(separator) + len(new_piece) > max_chunk_size
    ):
        overlap_pieces.pop(0)

    return overlap_pieces


def _merge_pieces(
    pieces: list[str],
    separator: str,
    max_chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Greedily combine pieces up to max_chunk_size maintaining configured chunk_overlap."""
    chunks: list[str] = []
    accumulator: list[str] = []
    current_length = 0

    for piece in pieces:
        added_len = len(separator) + len(piece) if accumulator else len(piece)
        if current_length + added_len <= max_chunk_size:
            accumulator.append(piece)
            current_length += added_len
            continue

        if accumulator:
            merged = separator.join(accumulator).strip()
            if merged:
                chunks.append(merged)

        overlap_pieces = _compute_overlap(
            accumulator, separator, chunk_overlap, piece, max_chunk_size
        )
        accumulator = [*overlap_pieces, piece]
        current_length = len(separator.join(accumulator))

    if accumulator:
        merged = separator.join(accumulator).strip()
        if merged:
            chunks.append(merged)

    return chunks


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
    chosen_separator, separator_index = _choose_separator(text, active_separators)

    # Fallback to character slicing when no delimiter or at terminal separator
    if chosen_separator == "":
        step = max(1, max_chunk_size - chunk_overlap)
        return [text[i : i + max_chunk_size] for i in range(0, len(text), step)]

    splits = text.split(chosen_separator)
    refined_pieces = _refine_splits(
        splits, separator_index, active_separators, max_chunk_size, chunk_overlap
    )
    return _merge_pieces(refined_pieces, chosen_separator, max_chunk_size, chunk_overlap)


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
        raw_content, base_meta = self._extract_document_input(document, metadata)
        if not raw_content or not raw_content.strip():
            return []

        sections = parse_markdown_sections(raw_content)
        chunks: list[DocumentChunk] = []

        for section in sections:
            new_chunks = self._create_section_chunks(section, base_meta, len(chunks))
            chunks.extend(new_chunks)

        return chunks

    @staticmethod
    def _extract_document_input(
        document: ExtractedDocument | str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Normalize extracted document or raw text string and base metadata."""
        if isinstance(document, ExtractedDocument):
            base_meta: dict[str, Any] = {
                "source_url": document.source_url,
                "document_title": document.title,
                **document.metadata,
            }
            content = document.content
        else:
            base_meta = {}
            content = str(document)

        if metadata:
            base_meta.update(metadata)
        return content, base_meta

    def _create_section_chunks(
        self,
        section: MarkdownSection,
        base_meta: dict[str, Any],
        start_index: int,
    ) -> list[DocumentChunk]:
        """Create single or recursive chunks for a given MarkdownSection."""
        content = section.content.strip()
        if not content:
            return []

        breadcrumb = " > ".join(section.heading_path) if section.heading_path else ""
        prefix = (
            self.breadcrumb_prefix.format(breadcrumb=breadcrumb)
            if self.inject_breadcrumbs and breadcrumb
            else ""
        )
        section_meta: dict[str, Any] = {
            **base_meta,
            "heading_path": list(section.heading_path),
            "breadcrumb": breadcrumb,
        }

        candidate_text = f"{prefix}{content}"
        if len(candidate_text) <= self.max_chunk_size:
            return [
                DocumentChunk(
                    chunk_index=start_index,
                    text=candidate_text,
                    metadata=section_meta,
                )
            ]

        return self._split_oversized_section(content, prefix, section_meta, start_index)

    def _split_oversized_section(
        self,
        content: str,
        prefix: str,
        section_meta: dict[str, Any],
        start_index: int,
    ) -> list[DocumentChunk]:
        """Recursively split oversized section content and wrap with breadcrumb prefix."""
        effective_max = max(50, self.max_chunk_size - len(prefix))
        effective_overlap = min(self.chunk_overlap, effective_max // 2)

        sub_splits = recursive_split_text(
            content,
            max_chunk_size=effective_max,
            chunk_overlap=effective_overlap,
        )

        chunks: list[DocumentChunk] = []
        for i, sub in enumerate(sub_splits):
            sub_text = f"{prefix}{sub}" if prefix else sub
            chunks.append(
                DocumentChunk(
                    chunk_index=start_index + i,
                    text=sub_text,
                    metadata=section_meta,
                )
            )
        return chunks
