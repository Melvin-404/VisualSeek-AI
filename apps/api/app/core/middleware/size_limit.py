from starlette.requests import Request
from fastapi import status
from app.core.exceptions import get_problem_details_response


class PayloadSizeLimitMiddleware:
    """Raw ASGI middleware validating Content-Length payload boundaries to prevent memory exhaustion.
    
    Bypasses BaseHTTPMiddleware to avoid breaking WebSocket handshake connections.
    """

    def __init__(self, app, default_limit_bytes: int = 2 * 1024 * 1024, video_limit_bytes: int = 100 * 1024 * 1024):
        self.app = app
        self.default_limit = default_limit_bytes
        self.video_limit = video_limit_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Resolve limit based on URL path
        path = scope.get("path", "")
        limit = self.default_limit
        if "/video/" in path or "/upload" in path:
            limit = self.video_limit

        # Validate Content-Length header from ASGI headers list
        headers = scope.get("headers", [])
        content_length = None
        for key, value in headers:
            if key == b"content-length":
                try:
                    content_length = int(value.decode("utf-8"))
                except ValueError:
                    # Invalid Content-Length header
                    request = Request(scope, receive)
                    response = get_problem_details_response(
                        request=request,
                        status_code=status.HTTP_400_BAD_REQUEST,
                        title="Bad Request",
                        detail="Invalid Content-Length header.",
                        error_type="https://errors.visionquery.ai/invalid-headers",
                    )
                    await response(scope, receive, send)
                    return
                break

        if content_length is not None and content_length > limit:
            limit_mb = limit / (1024 * 1024)
            request = Request(scope, receive)
            response = get_problem_details_response(
                request=request,
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                title="Payload Too Large",
                detail=f"Request payload size of {content_length} bytes exceeds the allowed limit of {limit_mb:.1f} MB.",
                error_type="https://errors.visionquery.ai/payload-too-large",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
