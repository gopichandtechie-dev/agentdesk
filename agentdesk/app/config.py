from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    GOOGLE_APPLICATION_CREDENTIALS: str = "/Users/gopichand/gcp-keys/agentdesk-dev-500305-b5bde7767b97.json"
    # secrets / connections
    gemini_api_key: str = ""
    database_url: str = ""
    gcs_bucket: str = ""
    firestore_project: str = "agentdesk-dev-500305"
    firebase_project_id: str = "agentdesk-dev-500305"

    # langfuse (optional)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # budgets / chunking
    max_upload_bytes: int = 10 * 1024 * 1024
    per_job_token_budget: int = 500_000
    embed_dim: int = 1536
    chunk_target_tokens: int = 1000
    chunk_overlap_tokens: int = 120
    max_rechunk_attempts: int = 3

    # local-dev only
    auth_debug: bool = False

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()