"""Markdown cleaning and sanitization utilities for extracted content."""

import re

# Regex for Wikipedia / web edit links: e.g. [edit], [edit | edit source], [edit](url), etc.
_EDIT_LINK_PATTERN = re.compile(
    r"\\?\[\s*(?:\\?\[)?\s*edit(?:\s*\|\s*edit\s+source)?\s*(?:\\?\])?\s*\\?\](?:\([^)]*\))?",
    re.IGNORECASE,
)

# Regex for citation markers: e.g. [1], [23], [note 1], [citation needed], [1](url)
_CITATION_PATTERN = re.compile(
    r"\\?\[\s*(?:\d+|note\s+\d+|citation\s+needed)\s*\\?\](?:\([^)]*\))?",
    re.IGNORECASE,
)

# Regex for empty markdown headings: e.g. '## ' or '###'
_EMPTY_HEADING_PATTERN = re.compile(r"^#{1,6}\s*$", re.MULTILINE)

# Regex for redundant blank lines: 3 or more consecutive newlines
_EXCESS_NEWLINES_PATTERN = re.compile(r"\n{3,}")


def remove_edit_links(text: str) -> str:
    """Remove section edit links commonly found in Wikipedia and wiki markdown."""
    return _EDIT_LINK_PATTERN.sub("", text)


def remove_citation_markers(text: str) -> str:
    """Remove numbered and note-based citation references (e.g. [1], [note 1])."""
    return _CITATION_PATTERN.sub("", text)


def remove_empty_headings(text: str) -> str:
    """Remove markdown headings that contain no title text."""
    return _EMPTY_HEADING_PATTERN.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Sanitize trailing spaces, multiple inter-word spaces, and excess blank lines."""
    lines = text.splitlines()
    cleaned_lines: list[str] = []
    for line in lines:
        stripped_line = line.rstrip()
        # Collapse multiple horizontal spaces if line is not indented code/list
        if stripped_line.startswith(("    ", "\t")):
            cleaned_lines.append(stripped_line)
        else:
            # Collapse internal repeated spaces while preserving initial single leading space if any
            leading_spaces = len(stripped_line) - len(stripped_line.lstrip(" "))
            indent = " " * leading_spaces
            collapsed = re.sub(r"[ \t]{2,}", " ", stripped_line.lstrip(" "))
            cleaned_lines.append(f"{indent}{collapsed}" if stripped_line else "")

    rejoined = "\n".join(cleaned_lines)
    collapsed_newlines = _EXCESS_NEWLINES_PATTERN.sub("\n\n", rejoined)
    return collapsed_newlines.strip()


def clean_markdown(text: str) -> str:
    """Clean and sanitize crawled markdown content.

    Applies edit link removal, citation marker stripping, empty heading cleanup,
    and whitespace normalization.

    Args:
        text: Raw markdown text.

    Returns:
        Sanitized, normalized markdown text.
    """
    if not text or not text.strip():
        return ""

    cleaned = remove_edit_links(text)
    cleaned = remove_citation_markers(cleaned)
    cleaned = remove_empty_headings(cleaned)
    return normalize_whitespace(cleaned)
