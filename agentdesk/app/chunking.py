from __future__ import annotations

import re

import tiktoken
from app.models import Chunk, Provenance

#gemini-embedding-001 hard input limit; we stay strictly below it.
EMBED_INPUT_LIMIT=2048
_HARD_CHUNK_CAP= EMBED_INPUT_LIMIT - 48 #safety margin for tokenizer skew

#cl100k_base is a stable, dependency-free proxy tokenizer for budgeting.
_ENC = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))

def _split_on_headings(text: str) -> list[str]:
    """Split Markdown on ATX headings so structural boundaries seed chunks."""
    parts= re.split(r"(?m)^(?=#{1,6}\s)", text)
    return [p for p in (p.strip() for p in parts if p) if p]

def _pack(segment: str, target: int, overlap: int, start_offset: int):
    """Token-window a single segment into <=cap pieces; yields (text, offset)."""
    cap = min(target, _HARD_CHUNK_CAP)
    tokens = _ENC.encode(segment)
    if not tokens:
        return
    step= max(1,cap-overlap)
    i = 0
    while i < len(tokens):
        window = tokens[i:i+cap]
        piece = _ENC.decode(window)
        yield piece, start_offset + i
        i += step

def chunk_text(
        rew_text: str,
        *,
        source: str,
        target_tokens: int,
        overlap_tokens: int,
        page_offsets: list[int] | None = None,
) -> list[Chunk]:
    """Heading-aware + token-window chunker.

    Guarantees every returned chunk has token_count <= _HARD_CHUNK_CAP (<2048),
    so the re-chunk look in the graph converges (AC-3).
    """
    chunks: list[Chunk] = []
    idx = 0

    if page_offsets is not None:
        #PDF: one segment per page, offset = page number (1-based).
         segments = [(t, page_offsets[i] if i<len(page_offsets) else i+1)
                     for i, t in enumerate(rew_text.split("\f"))]
    else:
         #Markdown: heading-delimited segments, offset = char position.
         segments,cursor = [],0
         for seg in _split_on_headings(rew_text):
             segments.append((seg, cursor))
             cursor += len(seg)

    for seg_text, seg_offset in segments:
        for piece, _tok_off in _pack(seg_text, target_tokens,overlap_tokens, seg_offset):
             tc= count_tokens(piece)
             if tc == 0:
                 continue
             chunks.append(
                 Chunk(
                     chunk_index=idx,
                     text=piece,
                     token_count=tc,
                     provenance=Provenance(source=source,offset=int(seg_offset), version=1),
                 )
            )
             idx += 1
    return chunks





