from __future__ import annotations
from functools import lru_cache

from google import genai
from google.cloud import firestore, storage
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from app.config import get_settings

@lru_cache
def gemini_client() -> genai.Client:
    s= get_settings()
    return genai.Client(api_key=s.gemini_api_key)

def _configure(conn) -> None:
   #Ensure the pgvector type adapter is registered on every pooled connection.
    register_vector(conn)

@lru_cache
def pg_pool() -> ConnectionPool:
    s=get_settings()
    return ConnectionPool(
        conninfo=s.database_url,
        max_size=4,
        min_size=0,
        configure=_configure,
        open=True,
    )
@lru_cache
def gcs_bucket():
    s=get_settings()
    return storage.Client(project=s.firestore_project).bucket(s.gcs_bucket)
@lru_cache
def firestore_client() -> firestore.Client:
    s=get_settings()
    print("Connecting to Firestore", s.firestore_project)
    return firestore.Client(project=s.firestore_project)
    return firestore.Client(project=s.firestore_project)
@lru_cache
def langfuse_client() :
    """ Return a Langfuse client, or None when tracing is disabled or unavailable.
     AC-10: tracing must never block ingestion, so any failure here return none.
     """
    s=get_settings()
    if not s.tracing_enabled:
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=s.langfuse_api_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
        )
    except Exception:
      return None


