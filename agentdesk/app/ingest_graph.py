from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from app.chunking import chunk_text, EMBED_INPUT_LIMIT, count_tokens
from app.clients import gemini_client, langfuse_client
from app.config import get_settings
from app.models import Chunk, IngestState
from app.persistence import write_chunks_atomic

EMBED_MODEL = "gemini-embedding-001"


def _trace(name: str, **meta) -> None:
    """Best-effort Langfuse span. Any failure is swallowed (AC-10)."""
    client = langfuse_client()
    if client is None:
        return
    try:
        client.event(name=name, metadata=meta)
    except Exception:
        pass


# ---- nodes -----------------------------------------------------------------

def parse_node(state: IngestState) -> IngestState:
    # Text is parsed in the route (needs the raw bytes); here we just seed loop state.
    s = get_settings()
    _trace("ingest.parse", job_id=state["job_id"], chars=len(state.get("raw_text", "")))
    return {"target_tokens": s.chunk_target_tokens, "attempts": 0}


def chunk_node(state: IngestState) -> IngestState:
    s = get_settings()
    chunks = chunk_text(
        state["raw_text"],
        source=state["filename"],
        target_tokens=state["target_tokens"],
        overlap_tokens=s.chunk_overlap_tokens,
        page_offsets=state.get("page_offsets"),
    )
    token_total = sum(c.token_count for c in chunks)
    _trace("ingest.chunk", job_id=state["job_id"],
           chunk_count=len(chunks), token_total=token_total, target=state["target_tokens"])
    return {"chunks": chunks, "token_total": token_total,
            "attempts": state.get("attempts", 0) + 1}


def validate_router(state: IngestState) -> str:
    """Conditional edge: 'embed' | 'rechunk' | 'fail'. Enforces AC-3/AC-4."""
    s = get_settings()
    chunks = state["chunks"]
    over_chunk = any(c.token_count >= EMBED_INPUT_LIMIT for c in chunks)
    over_job = state["token_total"] > s.per_job_token_budget
    has_provenance = all(
        c.provenance.source and c.provenance.version and c.provenance.offset is not None
        for c in chunks
    )

    if chunks and not over_chunk and not over_job and has_provenance:
        return "embed"
    if state["attempts"] >= s.max_rechunk_attempts:
        return "fail"
    return "rechunk"


def rechunk_node(state: IngestState) -> IngestState:
    # Re-plan: shrink the target by 25% and loop back to chunk (bounded by attempts).
    new_target = max(128, int(state["target_tokens"] * 0.75))
    _trace("ingest.rechunk", job_id=state["job_id"], new_target=new_target)
    return {"target_tokens": new_target}


def fail_node(state: IngestState) -> IngestState:
    s = get_settings()
    reason = ("token_budget_exceeded"
              if state["token_total"] > s.per_job_token_budget
              else "chunk_too_large")
    _trace("ingest.fail", job_id=state["job_id"], reason=reason)
    return {"status": "failed", "reason": reason}


def embed_node(state: IngestState) -> IngestState:
    s = get_settings()
    client = gemini_client()
    chunks: list[Chunk] = state["chunks"]

    # Batch to keep call count low; embed in groups of 100.
    for start in range(0, len(chunks), 100):
        batch = chunks[start : start + 100]
        last_err: Exception | None = None
        for attempt in range(3):                          # retry-with-backoff (AC-4/E4)
            try:
                resp = client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=[c.text for c in batch],
                    config={"task_type": "RETRIEVAL_DOCUMENT",
                            "output_dimensionality": s.embed_dim},
                )
                for c, emb in zip(batch, resp.embeddings):
                    c.embedding = _l2_normalize(list(emb.values))   # AC-6
                last_err = None
                break
            except Exception as e:                        # noqa: BLE001 - bounded retry
                last_err = e
        if last_err is not None:
            raise RuntimeError("embedding_unavailable") from last_err

    _trace("ingest.embed", job_id=state["job_id"], dim=s.embed_dim, count=len(chunks))
    return {"chunks": chunks}


def persist_node(state: IngestState) -> IngestState:
    written = write_chunks_atomic(state["tenant_id"], state["doc_id"], state["chunks"])
    _trace("ingest.persist", job_id=state["job_id"], rows=written)
    return {"status": "succeeded"}


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


# ---- graph -----------------------------------------------------------------

def build_ingest_graph():
    g = StateGraph(IngestState)
    g.add_node("parse", parse_node)
    g.add_node("chunk", chunk_node)
    g.add_node("rechunk", rechunk_node)
    g.add_node("fail", fail_node)
    g.add_node("embed", embed_node)
    g.add_node("persist", persist_node)

    g.add_edge(START, "parse")
    g.add_edge("parse", "chunk")
    g.add_conditional_edges(
        "chunk", validate_router,
        {"embed": "embed", "rechunk": "rechunk", "fail": "fail"},
    )
    g.add_edge("rechunk", "chunk")     # the bounded re-chunk loop
    g.add_edge("embed", "persist")
    g.add_edge("persist", END)
    g.add_edge("fail", END)
    return g.compile()


_GRAPH = None


def run_ingest(state: IngestState) -> IngestState:
    """Compile once, invoke per job. Returns the final state."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_ingest_graph()
    return _GRAPH.invoke(state, config={"configurable": {"thread_id": state["job_id"]}})