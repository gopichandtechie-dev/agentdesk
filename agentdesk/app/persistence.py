from __future__ import annotations

import json

from google.cloud import firestore

from app.clients import firestore_client, pg_pool
from app.models import Chunk


def write_chunks_atomic(tenant_id: str, doc_id: str, chunks: list[Chunk]) -> int:
    """Insert ALL chunks in ONE transaction. Commits everything or nothing (AC-7).

    Returns the number of rows written.
    """
    pool = pg_pool()
    with pool.connection() as conn:               # borrows a pooled connection
        with conn.transaction():                  # BEGIN ... COMMIT / ROLLBACK
            with conn.cursor() as cur:
                for ch in chunks:
                    cur.execute(
                        """
                        INSERT INTO kb_chunks
                          (tenant_id, doc_id, chunk_index, chunk_text,
                           embedding, fts, provenance, token_count)
                        VALUES
                          (%s, %s, %s, %s, %s,
                           to_tsvector('english', %s), %s::jsonb, %s)
                        """,
                        (
                            tenant_id,
                            doc_id,
                            ch.chunk_index,
                            ch.text,
                            ch.embedding,                       # pgvector adapter -> vector(1536)
                            ch.text,
                            json.dumps(ch.provenance.model_dump()),
                            ch.token_count,
                        ),
                    )
    return len(chunks)


def create_job(job_id: str, tenant_id: str, doc_id: str, filename: str, mime: str) -> None:
    firestore_client().collection("kb_jobs").document(job_id).set(
        {
            "tenant_id": tenant_id,
            "doc_id": doc_id,
            "filename": filename,
            "mime": mime,
            "status": "running",
            "reason": None,
            "chunk_count": None,
            "token_total": None,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )


def finish_job(job_id: str, *, status: str, chunk_count: int = 0,
               token_total: int = 0, reason: str | None = None) -> None:
    firestore_client().collection("kb_jobs").document(job_id).update(
        {
            "status": status,
            "chunk_count": chunk_count,
            "token_total": token_total,
            "reason": reason,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )