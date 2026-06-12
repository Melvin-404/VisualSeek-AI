# Architecture Decision Record (ADR)

## 1. FastAPI Observability, Middleware, and Rate Limiting

* **Date**: 2026-06-10
* **Status**: Accepted
* **Context**: VisionQuery AI requires a production-grade, secure, and observable backend foundation. Key needs include strict multi-tenant boundary checks, payload size caps to prevent memory exhaustion from video uploads, request correlation tracking across logs and traces, API rate limiting, and standard security headers.

---

## Decisions

### 1. Structured Logging
- **Decision**: Standardize on `structlog` for application logging.
- **Rationale**: Structlog allows us to log structured context (JSON format) in production, which is easily parsed by central log aggregators.
- **Detail**: In development, it falls back to a human-readable console renderer. Every log entry automatically injects `request_id` (correlation ID) and `tenant_id` (extracted from headers) from execution context.

### 2. Observability & Tracing
- **Decision**: Use OpenTelemetry with a Jaeger gRPC OTLP exporter for distributed tracing, and Prometheus metrics endpoint (`/metrics`) for telemetry.
- **Rationale**: OpenTelemetry is the open standard for vendor-neutral tracing. Prometheus provides lightweight performance counters (request counts, latency distributions) without adding overhead.
- **Detail**: Tracing initialization is wrapped in startup try/except blocks to prevent API startup crashes if OTLP collectors are offline.

### 3. Middleware Pipeline
- **Decision**: Chain custom middlewares in the following execution sequence (outermost to innermost):
  1. `RequestIdMiddleware`: Generates/reads `X-Request-ID` and stores it in context.
  2. `SecurityHeadersMiddleware`: Adds HSTS, CSP, X-Frame-Options, and X-Content-Type-Options.
  3. `PayloadSizeLimitMiddleware`: Rejects requests exceeding 100MB (for video uploads) or 2MB (for standard API payloads) with a `413 Payload Too Large`.
  4. `TenantIdMiddleware`: Rejects requests missing the `X-Tenant-ID` header with `400 Bad Request` (except on public routes like health and OpenAPI).
  5. `SlowAPIMiddleware`: Handles API rate limiting.

### 4. Rate Limiting Backend
- **Decision**: Use SlowAPI with Redis for distributed rate-limit state tracking.
- **Rationale**: A shared Redis instance ensures rate limits are respected across multiple API replica nodes in production.
- **Detail**: On startup, the limiter pings Redis. If Redis is unreachable, the system automatically falls back to in-memory rate limiting to ease local developer environments.

---

## Consequences

- **Pros**:
  - Log aggregation and request debugging are simplified via unified request IDs.
  - Multi-tenant leakage risks are blocked at the router entry point.
  - Mitigates DoS and out-of-memory vulnerabilities by capping incoming payload sizes before loading them into memory.
  - Self-healing rate limit fallback enables friction-free offline development.
- **Cons**:
  - Slight latency overhead from parsing headers and executing multiple middleware steps.
