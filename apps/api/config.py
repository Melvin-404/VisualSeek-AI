"""Module for API configuration and environment validation using Pydantic Settings.

This module validates backend environment variables at startup and exports a
Settings instance.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the FastAPI backend application."""

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
BasePort = 8000
