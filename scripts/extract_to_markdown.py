"""Utility script to invoke Crawl4AIExtractor and save extracted Markdown to disk.

Allows isolated testing of web crawling and markdown sanitization without
running the entire database, chunking, or background worker pipeline.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.exceptions import ExtractionError
from app.services.extractors.web import Crawl4AIExtractor


def derive_output_filename(url: str, title: str | None = None) -> str:
    """Derive a clean, safe filename from a URL or document title.

    Args:
        url: Target web URL.
        title: Optional page title.

    Returns:
        Sanitized filename ending in .md.
    """
    parsed = urlparse(url)
    path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]

    if path_segments:
        raw_name = path_segments[-1]
    elif title:
        raw_name = title
    else:
        raw_name = parsed.netloc or "extracted_document"

    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", raw_name).strip("_").lower()
    return f"{sanitized or 'extracted_document'}.md"


async def extract_and_save(
    url: str,
    output_path: str | Path | None = None,
    *,
    verbose: bool = True,
) -> Path:
    """Extract content from URL using Crawl4AIExtractor and save to a Markdown file.

    Args:
        url: Target URL to crawl.
        output_path: Destination path for the saved markdown. If omitted, derives
                     a filename in the current working directory.
        verbose: Whether to print progress messages to stdout.

    Returns:
        Path to the saved markdown file.
    """
    if verbose:
        print(f"Crawling URL: {url}")
        print("Launching Crawl4AI headless browser...")

    extractor = Crawl4AIExtractor()
    doc = await extractor.extract(url)

    if output_path is None:
        target_file = Path(derive_output_filename(url, doc.title))
    else:
        target_file = Path(output_path)

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(doc.content, encoding="utf-8")

    if verbose:
        token_estimate = max(1, len(doc.content) // 4)
        print("\n" + "=" * 60)
        print("Extraction Successful!")
        print("=" * 60)
        print(f"Title:        {doc.title}")
        print(f"Source URL:   {doc.source_url}")
        print(f"Language:     {doc.metadata.get('language', 'unknown')}")
        print(f"Content Size: {len(doc.content):,} characters (~{token_estimate:,} tokens)")
        print(f"Saved To:     {target_file.resolve()}")
        print("=" * 60)

    return target_file


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for extract_to_markdown."""
    parser = argparse.ArgumentParser(
        description="Extract and sanitize web content to a Markdown file using Crawl4AI.",
    )
    parser.add_argument(
        "url",
        help="Target web URL to extract (e.g. https://en.wikipedia.org/wiki/Ada_Lovelace)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output markdown file path (default: derived from URL/title)",
        default=None,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational stdout messages",
    )

    args = parser.parse_args(argv)

    try:
        asyncio.run(
            extract_and_save(
                url=args.url,
                output_path=args.output,
                verbose=not args.quiet,
            )
        )
        return 0
    except ExtractionError as exc:
        print(f"Extraction Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
