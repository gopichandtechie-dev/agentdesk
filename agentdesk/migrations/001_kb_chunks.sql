-- AgentDesk iteration-01 — kb_chunks (UC-04)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT          NOT NULL,
    doc_id      UUID          NOT NULL,
    chunk_index INT           NOT NULL,
    chunk_text  TEXT          NOT NULL,
    embedding   VECTOR(1536)  NOT NULL,
    fts         TSVECTOR      NOT NULL,
    provenance  JSONB         NOT NULL,
    token_count INT           NOT NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, doc_id, chunk_index)
);

-- tenant_id is the mandatory isolation filter (NFR-03); index it.
CREATE INDEX IF NOT EXISTS kb_chunks_tenant_idx ON kb_chunks (tenant_id);

-- dense ANN index (cosine) — used by UC-09 retrieval next iteration.
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);

-- sparse FTS index for hybrid retrieval.
CREATE INDEX IF NOT EXISTS kb_chunks_fts_idx ON kb_chunks USING gin (fts);