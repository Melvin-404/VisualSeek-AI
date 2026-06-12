import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from fastapi import Request
from app.main import app, limiter

# Mount temporary test routes on the FastAPI app (functions named to avoid pytest automatic test matching)
@app.post("/test-size-limit")
async def handle_mock_size_route():
    return {"ok": True}


@app.post("/api/v1/video/upload")
async def handle_mock_video_route():
    return {"ok": True}


@app.get("/test-rate-limit")
@limiter.limit("2/minute")
async def handle_mock_rate_route(request: Request):
    return {"ok": True}


@pytest.mark.asyncio
async def test_health_liveness():
    """Verifies that liveness endpoint bypasses tenant check and returns 200."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_health_gpu():
    """Verifies that GPU stats endpoint bypasses tenant checks and returns NVIDIA/GPU fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/gpu")
        assert response.status_code == 200
        data = response.json()
        assert "gpu_name" in data
        assert "memory_total_bytes" in data
        assert "memory_free_bytes" in data
        assert "status" in data


@pytest.mark.asyncio
async def test_request_id_middleware():
    """Asserts that X-Request-ID is generated and returned in headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test generated ID
        response = await ac.get("/health/live")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        generated_id = response.headers["X-Request-ID"]
        assert len(generated_id) > 10
        
        # 2. Test propagated ID
        custom_id = str(uuid.uuid4())
        response2 = await ac.get("/health/live", headers={"X-Request-ID": custom_id})
        assert response2.status_code == 200
        assert response2.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_tenant_id_middleware():
    """Asserts X-Tenant-ID header requirement on protected routes and validation bypass on public paths."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Protected route: missing header should return 400 Bad Request
        response = await ac.post("/test-size-limit")
        assert response.status_code == 400
        data = response.json()
        assert data["title"] == "Missing Tenant ID Header"
        assert data["status"] == 400
        assert "X-Request-ID" in response.headers
        
        # Protected route: valid header should bypass tenant rejection
        response2 = await ac.post("/test-size-limit", headers={"X-Tenant-ID": "tenant-abc"})
        assert response2.status_code == 200
        assert response2.json() == {"ok": True}


@pytest.mark.asyncio
async def test_payload_size_limit_middleware():
    """Asserts request body capping (2MB default, 100MB for video uploads)."""
    headers = {"X-Tenant-ID": "tenant-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Default route with small body should succeed
        res_small = await ac.post("/test-size-limit", headers=headers, content="x" * 100)
        assert res_small.status_code == 200
        
        # 2. Default route with > 2MB body should be blocked (2.1 MB)
        large_body = "x" * (2 * 1024 * 1024 + 100)
        headers_large = headers.copy()
        headers_large["Content-Length"] = str(len(large_body))
        
        res_large = await ac.post("/test-size-limit", headers=headers_large, content=large_body)
        assert res_large.status_code == 413
        assert res_large.json()["title"] == "Payload Too Large"
        
        # 3. Video upload route with 5MB body should succeed (limit is 100MB)
        video_body = "v" * (5 * 1024 * 1024)
        headers_video = headers.copy()
        headers_video["Content-Length"] = str(len(video_body))
        
        res_video = await ac.post("/api/v1/video/upload", headers=headers_video, content=video_body)
        assert res_video.status_code == 200


@pytest.mark.asyncio
async def test_security_headers_middleware():
    """Asserts standard transport-level security headers are injected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/live")
        assert response.status_code == 200
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains; preload"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "Content-Security-Policy" in response.headers


@pytest.mark.asyncio
async def test_cors_middleware():
    """Asserts CORS headers are present for whitelisted enterprise domains."""
    whitelisted_origin = "http://localhost:3000"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/health/live",
            headers={
                "Origin": whitelisted_origin,
                "Access-Control-Request-Method": "GET"
            }
        )
        assert response.headers.get("Access-Control-Allow-Origin") == whitelisted_origin
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"


@pytest.mark.asyncio
async def test_rate_limiting_middleware():
    """Asserts client rate limiting blocks rapid successive requests on limited endpoints."""
    headers = {"X-Tenant-ID": "test-tenant"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res1 = await ac.get("/test-rate-limit", headers=headers)
        assert res1.status_code == 200
        
        res2 = await ac.get("/test-rate-limit", headers=headers)
        assert res2.status_code == 200
        
        res3 = await ac.get("/test-rate-limit", headers=headers)
        assert res3.status_code == 429
        assert res3.json()["title"] == "Rate Limit Exceeded"
