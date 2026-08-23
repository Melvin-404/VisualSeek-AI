import os
import socket

# Force offline model loading to prevent Hugging Face Hub timeouts
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Restrict default socket connection timeouts to 3.0s (triggers local fallbacks instantly if network hangs)
socket.setdefaulttimeout(3.0)

import logging
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import (
    register_exception_handlers,
    correlation_id_ctx,
    tenant_id_ctx,
    get_problem_details_response,
)
from app.core.middleware.request_id import RequestIdMiddleware
from app.core.middleware.tenant import TenantIdMiddleware
from app.core.middleware.security_headers import SecurityHeadersMiddleware
from app.core.middleware.size_limit import PayloadSizeLimitMiddleware
from app.api.v1.routers import health, auth, search, chat, analytics, cameras


# 1. Structured Logging Configuration (structlog)
def inject_contextvars_processor(logger, method_name, event_dict):
    """structlog processor injecting request correlation ID and tenant context."""
    req_id = correlation_id_ctx.get()
    tenant_id = tenant_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id
    if tenant_id:
        event_dict["tenant_id"] = tenant_id
    return event_dict


def configure_logging():
    """Configures structlog to render JSON in production or clean console logs in development."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        inject_contextvars_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.API_ENV.lower() in ["production", "staging"]:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge standard logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


configure_logging()
logger = structlog.get_logger("main")


# 2. Rate Limiting Setup (SlowAPI with Redis Fallback)
def get_rate_limiter() -> Limiter:
    """Configures SlowAPI Limiter with Redis storage, falling back to Memory if unreachable."""
    storage_uri = settings.REDIS_URL
    try:
        # Test connection synchronously for configuration fallback
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, socket_timeout=1.0)
        r.ping()
        r.close()
        logger.info("Successfully connected to Redis rate limiting storage.")
    except Exception as e:
        logger.warning("Redis unavailable. Falling back to in-memory rate limiting.", error=str(e))
        storage_uri = "memory://"

    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        default_limits=["100 per minute"],
    )


limiter = get_rate_limiter()


# 3. OpenTelemetry / Jaeger Configuration
def setup_opentelemetry(app: FastAPI):
    """Sets up OpenTelemetry tracing and instruments the FastAPI app instance."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Define Tracer Provider
        provider = TracerProvider()
        
        # OTLP Collector Endpoint
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        
        trace.set_tracer_provider(provider)
        
        # Instrument App
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry tracing instrumentation successfully configured.")
    except Exception as e:
        logger.warning("OpenTelemetry tracing initialization skipped or failed.", error=str(e))


# 4. Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifecycle manager executing startup and shutdown resource logic."""
    logger.info("Application starting up... verifying DB connectivity...")
    
    # Verify DB connectivity on startup
    from app.db.session import engine
    from sqlalchemy import text
    try:
        logger.info("Before async with engine.connect()")
        async with engine.connect() as conn:
            logger.info("Before conn.execute(SELECT 1)")
            await conn.execute(text("SELECT 1"))
            logger.info("After conn.execute(SELECT 1)")
        logger.info("Database connection verified successfully.")
    except Exception as e:
        logger.critical("Database connection failed on startup!", error=str(e))

    yield

    logger.info("Application shutting down...")
    # Clean up DB connections pool
    await engine.dispose()
    logger.info("Database connection pool disposed.")


# Initialize FastAPI app
app = FastAPI(
    title="VisualSeek AI API",
    description="Enterprise-grade backend API for VisualSeek AI",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Exception handlers
register_exception_handlers(app)

# Register slowapi rate limit exception handler
app.state.limiter = limiter
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request, exc):
    return get_problem_details_response(
        request=request,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        title="Rate Limit Exceeded",
        detail=f"Rate limit exceeded: {exc.detail}",
        error_type="https://errors.visionquery.ai/rate-limit-exceeded",
    )

# Register OpenTelemetry
setup_opentelemetry(app)

# Prometheus metrics instrumentation (/metrics)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Add Middlewares in order of execution (Outer to Inner)
# In FastAPI, last added is executed first (outermost).
# app.add_middleware(SlowAPIMiddleware)
app.add_middleware(TenantIdMiddleware)
app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers (API Versioning Strategy)
app.include_router(health.router) # Root level health check bypass
app.include_router(auth.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(search.detections_router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(cameras.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1") # Also register versioned health endpoint
