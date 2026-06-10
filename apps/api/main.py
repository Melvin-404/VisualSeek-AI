"""Main entry point for the FastAPI backend application.

This module initializes the FastAPI app, configures standard middleware,
and exposes a health check endpoint.
"""

from fastapi import FastAPI, status
from config import settings

app = FastAPI(
    title="Vision Query API",
    description="Enterprise-grade backend API for Vision Query",
    version="1.0.0",
)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness and readiness check endpoint.

    Returns:
        dict: A status check indicating the API is healthy.
    """
    return {
        "status": "healthy",
        "environment": settings.API_ENV,
    }
