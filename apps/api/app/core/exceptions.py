from contextvars import ContextVar
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

logger = structlog.get_logger("exceptions")

# Thread-local / Async correlation context var
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id_ctx", default="")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id_ctx", default="")


def get_problem_details_response(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    error_type: str = "about:blank",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Builds a standardized RFC 7807 ProblemDetails response payload.
    
    Args:
        request: The active incoming request.
        status_code: Target HTTP status code.
        title: Short error title.
        detail: Human-readable error description.
        error_type: Reference URI.
        extra_fields: Additional fields to merge (e.g. validation issues).
        
    Returns:
        JSONResponse: Standardized JSON payload.
    """
    req_id = correlation_id_ctx.get()
    
    problem = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "request_id": req_id if req_id else None,
    }
    
    if extra_fields:
        problem.update(extra_fields)
        
    headers = {"Content-Type": "application/problem+json"}
    if req_id:
        headers["X-Request-ID"] = req_id
        
    return JSONResponse(
        status_code=status_code,
        content=problem,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handles standard Starlette/FastAPI HTTPExceptions."""
    # Retrieve detail string safely
    detail = exc.detail if hasattr(exc, "detail") else str(exc)
    
    logger.warning("HTTP error occurred", status_code=exc.status_code, detail=detail, path=request.url.path)
    
    return get_problem_details_response(
        request=request,
        status_code=exc.status_code,
        title="HTTP Error",
        detail=detail,
        error_type=f"https://errors.visionquery.ai/http-{exc.status_code}",
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles Pydantic validation errors."""
    detail = "Request validation failed."
    errors: List[Dict[str, Any]] = []
    
    for err in exc.errors():
        # Clean loc representation
        loc = " -> ".join(str(loc) for loc in err["loc"])
        errors.append({
            "field": loc,
            "message": err["msg"],
            "type": err["type"]
        })
        
    logger.warning("Validation error occurred", errors=errors, path=request.url.path)
    
    return get_problem_details_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail=detail,
        error_type="https://errors.visionquery.ai/validation-error",
        extra_fields={"invalid_params": errors},
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handles database exceptions, obscuring raw connection strings or queries."""
    # We log the raw exception details securely
    logger.error("Database query exception", error=str(exc), path=request.url.path)
    
    return get_problem_details_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Database Error",
        detail="A secure database error occurred while processing the request.",
        error_type="https://errors.visionquery.ai/database-error",
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handles uncaught system exceptions."""
    logger.exception("Internal server uncaught exception", error=str(exc), path=request.url.path)
    
    return get_problem_details_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected error occurred. Please contact system administrators.",
        error_type="https://errors.visionquery.ai/internal-error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers to the FastAPI app instance."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
