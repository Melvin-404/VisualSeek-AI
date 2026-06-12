class SecurityHeadersMiddleware:
    """Raw ASGI middleware applying mandatory security headers to all HTTP responses.
    
    Bypasses BaseHTTPMiddleware to avoid breaking WebSocket handshake connections.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                # Security headers to inject
                security_headers = [
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"content-security-policy", b"default-src 'self'; frame-ancestors 'none';"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ]
                
                # Prevent duplicates by filtering existing headers
                security_keys = {sh[0] for sh in security_headers}
                filtered_headers = [h for h in headers if h[0].lower() not in security_keys]
                
                # Append security headers
                filtered_headers.extend(security_headers)
                message["headers"] = filtered_headers
                
            await send(message)

        await self.app(scope, receive, send_wrapper)
