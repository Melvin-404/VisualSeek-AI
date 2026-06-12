import uuid
from app.core.exceptions import correlation_id_ctx


class RequestIdMiddleware:
    """Raw ASGI middleware for injecting and propagating request correlation IDs.
    
    Bypasses BaseHTTPMiddleware to preserve asyncio ContextVar context propagation.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Extract X-Request-ID from ASGI headers
        request_id = None
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                request_id = value.decode("utf-8")
                break
        
        if not request_id:
            request_id = str(uuid.uuid4())

        # 2. Bind to thread/async safe ContextVar
        token = correlation_id_ctx.set(request_id)

        # 3. Intercept send to append X-Request-ID response header
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Append correlation header if not already present
                has_header = any(k.lower() == b"x-request-id" for k, v in headers)
                if not has_header:
                    headers.append((b"x-request-id", request_id.encode("utf-8")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            correlation_id_ctx.reset(token)
