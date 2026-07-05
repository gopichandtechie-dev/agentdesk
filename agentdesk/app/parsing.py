from __future__ import annotations

import io


class ParseError(Exception):
    """Raised when a supported file cannot be decoded/parsed."""


def parse_markdown(data: bytes, filename: str) -> tuple[str, None]:
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError as e:
        raise ParseError(f"{filename}: not valid UTF-8") from e


def parse_pdf(data: bytes, filename: str) -> tuple[str, list[int]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except (PdfReadError, OSError, ValueError) as e:
        raise ParseError(f"{filename}: unreadable PDF") from e

    if not any(s.strip() for s in pages):
        raise ParseError(f"{filename}: no extractable text")

    # \f separates pages so the chunker can map page -> provenance offset.
    text = "\f".join(pages)
    page_offsets = list(range(1, len(pages) + 1))
    return text, page_offsets


def parse_upload(data: bytes, filename: str, mime: str):
    """Dispatch by extension. Returns (text, page_offsets_or_None)."""
    name = filename.lower()
    if name.endswith(".md"):
        return parse_markdown(data, filename)
    if name.endswith(".pdf"):
        return parse_pdf(data, filename)
    raise ParseError(f"{filename}: unsupported type {mime}")