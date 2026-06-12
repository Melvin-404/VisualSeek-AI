import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the FastAPI backend application."""

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_ENV: str = "development"

    # Database settings
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5435/postgres"

    # Encryption key for PII data (Fernet key)
    ENCRYPTION_KEY: str = "ba58mDwB9gULkdH9B7Ljy79q_0dLuRdSEdcYrtRe2p8="

    # Redis configuration for rate limiting
    REDIS_URL: str = "redis://localhost:6379/0"

    # Milvus Vector Store settings
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    MILVUS_POOL_SIZE: int = 1
    MILVUS_FEDERATED_INSTANCES: List[str] = []  # List of secondary milvus instances, e.g. ["host2:19530"]


    # OpenTelemetry / Jaeger configuration
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "visionquery-api"

    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ]

    # Security / JWT settings
    JWT_SECRET_KEY: str = "supersecretjwtkeyforvisionquerybackendapiwhichshouldbechangedinprod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Keycloak settings
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "visionquery"
    KEYCLOAK_CLIENT_ID: str = "visionquery-api"

    # --- LLM / NL Query Pipeline settings ---
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "openai"  # "openai", "anthropic", or "llama"
    LLAMA_API_URL: Optional[str] = None  # OpenAI-compatible base URL for local Llama
    LLM_TIMEOUT: float = 10.0
    LLM_MAX_RETRIES: int = 3
    LLM_MODEL_OPENAI: str = "gpt-4o"
    LLM_MODEL_ANTHROPIC: str = "claude-3-5-sonnet-20241022"
    LLM_MODEL_LLAMA: str = "meta-llama/Llama-3.1-70B-Instruct"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]


settings = Settings()
