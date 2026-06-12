import pytest
import uuid
import datetime
from fastapi import Depends
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import TokenPayload, get_current_user_payload, create_access_token, hash_api_key
from app.core.auth.permissions import require_permission
from app.core.rbac.policies import check_camera_access
from app.core.auth.keycloak import (
    is_account_locked_out,
    increment_failed_attempts,
    reset_failed_attempts,
    is_token_blacklisted,
    blacklist_token,
    get_redis_client
)
from app.models.schema_models import Organization, Camera, CameraAssignment, ApiKey, User
from app.core.rbac.roles import RoleEnum

# Add temporary test routes to the app for endpoint integration testing
# Use prefix "handle_mock_" to avoid pytest discovery warnings
@app.get("/test-permission-check")
async def handle_mock_permission_route(current_user: TokenPayload = require_permission("camera:read")):
    return {"ok": True, "sub": current_user.sub, "role": current_user.role}

@app.get("/test-permission-check-alert")
async def handle_mock_permission_alert_route(current_user: TokenPayload = require_permission("alert:manage")):
    return {"ok": True, "sub": current_user.sub, "role": current_user.role}

@app.get("/test-camera-check/{camera_id}")
async def handle_mock_camera_route(camera_id: uuid.UUID, camera = Depends(check_camera_access)):
    return {"ok": True, "camera_name": camera.name}

@app.get("/test-auth-payload")
async def handle_mock_payload_route(current_user: TokenPayload = Depends(get_current_user_payload)):
    return {"ok": True, "scopes": current_user.scopes, "tenant_id": current_user.tenant_id}


@pytest.mark.asyncio
async def test_hs256_token_validation_success():
    """Asserts that a valid local HS256 token resolves successfully."""
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    token_payload = {
        "sub": user_id,
        "tenant_id": org_id,
        "role": "analyst",
        "scopes": ["camera:read", "query:execute"]
    }
    token = create_access_token(token_payload)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/test-auth-payload", 
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": org_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == org_id
        assert "camera:read" in data["scopes"]


@pytest.mark.asyncio
async def test_rs256_token_validation_mocked():
    """Asserts RS256 token verification behaves correctly when JWKS public key is mocked."""
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    token_payload = {
        "sub": user_id,
        "tenant_id": org_id,
        "realm_access": {"roles": ["operator"]},
        "scope": "openid camera:read alert:manage",
        "exp": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).timestamp(),
        "jti": str(uuid.uuid4())
    }
    
    # Mocking decode_and_verify_token to bypass real Keycloak network request
    from unittest.mock import patch
    with patch("app.core.auth.jwt.decode_and_verify_token", return_value=token_payload):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/test-auth-payload", 
                headers={"Authorization": "Bearer fake_rs256_token", "X-Tenant-ID": org_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["tenant_id"] == org_id
            assert "camera:read" in data["scopes"]


@pytest.mark.asyncio
async def test_permission_checker():
    """Verifies that require_permission enforces roles/scopes mapping or blocks requests."""
    # 1. Access allowed (role mapping)
    token_payload = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "role": "analyst",  # Analyst has camera:read mapped in roles.py
        "scopes": []
    }
    token = create_access_token(token_payload)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/test-permission-check", 
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": token_payload["tenant_id"]}
        )
        assert response.status_code == 200
        
        # 2. Access blocked (role has no permission)
        token_payload2 = {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "viewer",  # Viewer does NOT have alert:manage permission
            "scopes": []
        }
        token2 = create_access_token(token_payload2)
        
        response2 = await ac.get(
            "/test-permission-check-alert", 
            headers={"Authorization": f"Bearer {token2}", "X-Tenant-ID": token_payload2["tenant_id"]}
        )
        assert response2.status_code == 403


@pytest.mark.asyncio
async def test_redis_lockout_policy():
    """Asserts that lockout state transitions correctly in Redis after 5 failures."""
    username = f"test_user_{uuid.uuid4().hex}@visionquery.ai"
    
    # Assert initially not locked out
    assert not await is_account_locked_out(username)
    
    # Perform 4 failures
    for i in range(4):
        attempts = await increment_failed_attempts(username)
        assert attempts == i + 1
        assert not await is_account_locked_out(username)
        
    # The 5th failure triggers lockout
    attempts = await increment_failed_attempts(username)
    assert attempts == 5
    assert await is_account_locked_out(username)
    
    # Successful login resets the lockout
    await reset_failed_attempts(username)
    assert not await is_account_locked_out(username)


@pytest.mark.asyncio
async def test_redis_token_blacklist():
    """Asserts that blacklisting/revocation blocks tokens."""
    token_payload = {
        "sub": str(uuid.uuid4()),
        "jti": str(uuid.uuid4()),
        "exp": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).timestamp()
    }
    
    # 1. Initially not blacklisted
    assert not await is_token_blacklisted(token_payload)
    
    # 2. Blacklist the token
    await blacklist_token(token_payload, expires_in=10)
    assert await is_token_blacklisted(token_payload)
    
    # Clean up blacklist key in Redis
    redis = get_redis_client()
    await redis.delete(f"token:blacklist:{token_payload['jti']}")
    await redis.close()


@pytest.mark.asyncio
async def test_camera_isolation_policies():
    """Enforces multi-tenancy and Operator-specific camera assignment rules in PostgreSQL."""
    from app.db.session import async_session_maker
    from sqlalchemy import text
    
    org_id = uuid.uuid4()
    camera_id = uuid.uuid4()
    operator_id = uuid.uuid4()
    
    # 1. Create Organization, User, and Camera for Org A inside a single transaction
    async with async_session_maker() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
            
            org_a = Organization(id=org_id, name="Organization A")
            session.add(org_a)
            await session.flush()
            
            user_a = User(
                id=operator_id,
                org_id=org_id,
                email=f"operator_{operator_id.hex}@visionquery.ai",
                hashed_password="some_hashed_password"
            )
            camera_a = Camera(
                id=camera_id,
                org_id=org_id,
                name="Front Lobby Camera",
                location="Reception",
                rtsp_url="rtsp://localhost/stream",
                status="online"
            )
            session.add(user_a)
            session.add(camera_a)
        
    try:
        # 2. Test Super Admin: Bypasses tenant check
        super_admin_payload = {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),  # different org id
            "role": RoleEnum.SUPER_ADMIN.value,
            "scopes": []
        }
        token_super = create_access_token(super_admin_payload)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Super admin should be allowed access when requesting under the target tenant
            res = await ac.get(
                f"/test-camera-check/{camera_id}", 
                headers={"Authorization": f"Bearer {token_super}", "X-Tenant-ID": str(org_id)}
            )
            assert res.status_code == 200
            assert res.json()["camera_name"] == "Front Lobby Camera"
            
            # 3. Test Org B Admin: Blocked (tenant mismatch)
            org_b_admin_payload = {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),  # Org B
                "role": RoleEnum.ORG_ADMIN.value,
                "scopes": []
            }
            token_b_admin = create_access_token(org_b_admin_payload)
            res_b = await ac.get(
                f"/test-camera-check/{camera_id}", 
                headers={"Authorization": f"Bearer {token_b_admin}", "X-Tenant-ID": org_b_admin_payload["tenant_id"]}
            )
            assert res_b.status_code == 403
            
            # 4. Test Org A Operator: Blocked initially (no camera assignment)
            operator_payload = {
                "sub": str(operator_id),
                "tenant_id": str(org_id),
                "role": RoleEnum.OPERATOR.value,
                "scopes": []
            }
            token_operator = create_access_token(operator_payload)
            res_op_blocked = await ac.get(
                f"/test-camera-check/{camera_id}", 
                headers={"Authorization": f"Bearer {token_operator}", "X-Tenant-ID": str(org_id)}
            )
            assert res_op_blocked.status_code == 403
            assert "not assigned to this camera" in res_op_blocked.json()["detail"]
            
            # 5. Add Camera Assignment for Operator
            async with async_session_maker() as session:
                async with session.begin():
                    await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
                    assignment = CameraAssignment(
                        user_id=operator_id,
                        camera_id=camera_id
                    )
                    session.add(assignment)
                
            # Now operator access should succeed
            res_op_allowed = await ac.get(
                f"/test-camera-check/{camera_id}", 
                headers={"Authorization": f"Bearer {token_operator}", "X-Tenant-ID": str(org_id)}
            )
            assert res_op_allowed.status_code == 200
            assert res_op_allowed.json()["camera_name"] == "Front Lobby Camera"
            
    finally:
        # Cleanup test data inside transaction (disabling audit log and other triggers temporarily)
        async with async_session_maker() as session:
            async with session.begin():
                await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
                await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE organizations DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE cameras DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE users DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE camera_assignments DISABLE TRIGGER ALL"))
                try:
                    await session.execute(
                        text("DELETE FROM camera_assignments WHERE camera_id = :camera_id"), 
                        {"camera_id": camera_id}
                    )
                    await session.execute(
                        text("DELETE FROM cameras WHERE id = :camera_id"), 
                        {"camera_id": camera_id}
                    )
                    await session.execute(
                        text("DELETE FROM users WHERE org_id = :org_id"),
                        {"org_id": org_id}
                    )
                    await session.execute(
                        text("DELETE FROM audit_log WHERE org_id = :org_id"),
                        {"org_id": org_id}
                    )
                    await session.execute(
                        text("DELETE FROM organizations WHERE id = :org_id"), 
                        {"org_id": org_id}
                    )
                finally:
                    await session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE organizations ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE cameras ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE users ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE camera_assignments ENABLE TRIGGER ALL"))


@pytest.mark.asyncio
async def test_api_key_authentication():
    """Asserts that service-to-service requests using X-API-Key validate successfully."""
    from app.db.session import async_session_maker
    from sqlalchemy import text
    
    org_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    raw_key = f"vq_live_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    hashed_key = hash_api_key(raw_key)
    
    async with async_session_maker() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
            
            org = Organization(id=org_id, name="Service Org")
            session.add(org)
            await session.flush()
            
            api_key_record = ApiKey(
                id=api_key_id,
                org_id=org_id,
                name="Test Pipeline Key",
                key_hash=hashed_key,
                scopes=["camera:read", "query:execute"],
                is_active=True,
                expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
            )
            session.add(api_key_record)
        
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Valid API Key check
            res = await ac.get(
                "/test-auth-payload", 
                headers={"X-API-Key": raw_key, "X-Tenant-ID": str(org_id)}
            )
            assert res.status_code == 200
            data = res.json()
            assert "camera:read" in data["scopes"]
            assert "query:execute" in data["scopes"]
            
            # 2. Deactivated API Key check
            async with async_session_maker() as session:
                async with session.begin():
                    await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
                    await session.execute(
                        text("UPDATE api_keys SET is_active = false WHERE id = :id"),
                        {"id": api_key_id}
                    )
                
            res_deactivated = await ac.get(
                "/test-auth-payload", 
                headers={"X-API-Key": raw_key, "X-Tenant-ID": str(org_id)}
            )
            assert res_deactivated.status_code == 401
            
    finally:
        async with async_session_maker() as session:
            async with session.begin():
                await session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
                await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE organizations DISABLE TRIGGER ALL"))
                await session.execute(text("ALTER TABLE api_keys DISABLE TRIGGER ALL"))
                try:
                    await session.execute(
                        text("DELETE FROM api_keys WHERE id = :id"),
                        {"id": api_key_id}
                    )
                    await session.execute(
                        text("DELETE FROM audit_log WHERE org_id = :org_id"),
                        {"org_id": org_id}
                    )
                    await session.execute(
                        text("DELETE FROM organizations WHERE id = :org_id"),
                        {"org_id": org_id}
                    )
                finally:
                    await session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE organizations ENABLE TRIGGER ALL"))
                    await session.execute(text("ALTER TABLE api_keys ENABLE TRIGGER ALL"))
