from fastapi import status
from starlette.requests import Request
from app.core.exceptions import tenant_id_ctx, get_problem_details_response


class TenantIdMiddleware:
    """Raw ASGI middleware enforcing and propagating tenant ID headers.
    
    Bypasses BaseHTTPMiddleware to preserve asyncio ContextVar context propagation.
    """

    def __init__(self, app, public_paths=None):
        self.app = app
        self.public_paths = public_paths or [
            "/health",
            "/health/live",
            "/health/ready",
            "/health/gpu",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth",
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        
        # Check if the requested route is a public bypass path
        is_public = False
        for pub_path in self.public_paths:
            if path == pub_path or path.startswith(pub_path + "/"):
                is_public = True
                break

        if is_public:
            await self.app(scope, receive, send)
            return

        # Extract X-Tenant-ID from ASGI headers
        tenant_id = None
        for key, value in scope.get("headers", []):
            if key == b"x-tenant-id":
                tenant_id = value.decode("utf-8")
                break

        if not tenant_id:
            # Construct standard Request object to satisfy the helper signature
            request = Request(scope, receive)
            response = get_problem_details_response(
                request=request,
                status_code=status.HTTP_400_BAD_REQUEST,
                title="Missing Tenant ID Header",
                detail="Multi-tenancy requires the 'X-Tenant-ID' HTTP header on this endpoint.",
                error_type="https://errors.visionquery.ai/missing-tenant-id",
            )
            # Run the response as an ASGI app to return it directly
            await response(scope, receive, send)
            return

        # Bind tenant_id to context variable
        token = tenant_id_ctx.set(tenant_id)
        try:
            await self.app(scope, receive, send)
        finally:
            tenant_id_ctx.reset(token)
