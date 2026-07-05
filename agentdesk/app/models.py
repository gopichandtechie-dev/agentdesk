from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str            # filename
    offset: int            # char offset (markdown) or page number (pdf)
    version: int = 1       # bumped by UC-05 re-index later; always present (AC-2)


class Chunk(BaseModel):
    chunk_index: int
    text: str = Field(min_length=1)
    token_count: int
    provenance: Provenance
    embedding: list[float] | None = None   # filled by the embed node


class JobResult(BaseModel):
    job_id: str
    doc_id: str
    status: Literal["succeeded", "failed"]
    chunk_count: int = 0
    token_total: int = 0
    reason: str | None = None


class IngestState(TypedDict, total=False):
    # inputs
    tenant_id: str
    doc_id: str
    job_id: str
    filename: str
    mime: str
    raw_text: str
    page_offsets: list[int]          # for pdf provenance
    # working state
    target_tokens: int
    attempts: int
    chunks: list[Chunk]
    token_total: int
    # outcome
    status: str                      # "running" | "succeeded" | "failed"
    reason: str | None