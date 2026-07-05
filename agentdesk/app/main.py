from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status

from app.auth import Caller, resolve_caller
from app.clients import gcs_bucket
from app.config import get_settings
from app.ingest_graph import run_ingest
from app.models import IngestState, JobResult
from app.parsing import ParseError, parse_upload
from app.persistence import create_job, finish_job

app = FastAPI(title="AgentDesk — KB Ingestion (UC-04)", version="0.1.0")

_MIME = {".md": "text/markdown", ".pdf": "application/pdf"}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/v1/kb/ingest", response_model=JobResult, status_code=status.HTTP_201_CREATED)
async def ingest(
    file: UploadFile = File(...),
    caller: Caller = Depends(resolve_caller),     # AC-8: 401/403 before any work
) -> JobResult:
    s = get_settings()
    name = (file.filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""

    # --- validate upload BEFORE any GCS/DB/job write (AC-9) ---
    if ext not in _MIME:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported file type")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    if len(data) > s.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    blob_path = f"kb_originals/{caller.tenant_id}/{doc_id}/{file.filename}"
    blob = gcs_bucket().blob(blob_path)

    # --- store original + open job record ---
    blob.upload_from_string(data, content_type=_MIME[ext])
    create_job(job_id, caller.tenant_id, doc_id, file.filename, _MIME[ext])

    try:
        text, page_offsets = parse_upload(data, file.filename, _MIME[ext])
    except ParseError as e:
        # E2/AC-5: unparseable -> fail clean, delete blob, no DB rows.
        _safe_delete(blob)
        finish_job(job_id, status="failed", reason=str(e))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    state: IngestState = {
        "tenant_id": caller.tenant_id,
        "doc_id": doc_id,
        "job_id": job_id,
        "filename": file.filename,
        "mime": _MIME[ext],
        "raw_text": text,
        "page_offsets": page_offsets,
    }

    try:
        final = run_ingest(state)
    except Exception as e:                         # embedding/DB failure (E3/E4/AC-4/AC-7)
        _safe_delete(blob)
        finish_job(job_id, status="failed", reason=str(e) or "ingest_error")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ingest failed; rolled back")

    if final.get("status") != "succeeded":
        # circuit-breaker tripped (AC-4): no rows were written by the graph.
        _safe_delete(blob)
        reason = final.get("reason", "ingest_failed")
        finish_job(job_id, status="failed", reason=reason)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, reason)

    chunk_count = len(final["chunks"])
    token_total = final["token_total"]
    finish_job(job_id, status="succeeded", chunk_count=chunk_count, token_total=token_total)

    return JobResult(
        job_id=job_id, doc_id=doc_id, status="succeeded",
        chunk_count=chunk_count, token_total=token_total,
    )


def _safe_delete(blob) -> None:
    try:
        blob.delete()
    except Exception:
        pass    # blob may not exist; never mask the original failure