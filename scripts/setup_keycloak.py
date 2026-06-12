import sys
import httpx

KEYCLOAK_URL = "http://localhost:8080"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"

def setup_keycloak():
    client = httpx.Client(timeout=10.0)
    
    # 1. Get Admin Token
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    token_data = {
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
        "grant_type": "password"
    }
    try:
        r = client.post(token_url, data=token_data)
        r.raise_for_status()
        token = r.json()["access_token"]
        print("Obtained admin token. Setting up realm 'visionquery'...")
    except Exception as e:
        print(f"Error getting admin token: {e}")
        if 'r' in locals() and r.text:
            print(f"Response: {r.text}")
        return False
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 2. Check if realm exists, if not create minimal, then update brute force settings
    realm_url = f"{KEYCLOAK_URL}/admin/realms/visionquery"
    r = client.get(realm_url, headers=headers)
    if r.status_code == 200:
        print("Realm 'visionquery' already exists.")
    else:
        # Create Realm with minimal fields
        create_realm_url = f"{KEYCLOAK_URL}/admin/realms"
        r = client.post(create_realm_url, json={"realm": "visionquery", "enabled": True}, headers=headers)
        if r.status_code in [200, 201, 204]:
            print("Realm 'visionquery' created successfully.")
        else:
            print(f"Failed to create realm: {r.status_code} - {r.text}")
            return False
            
    # Update realm with correct brute force detection settings (use failureFactor instead of maxLoginFailures)
    update_payload = {
        "realm": "visionquery",
        "displayName": "Vision Query",
        "enabled": True,
        "bruteForceProtected": True,
        "failureFactor": 5,
        "waitIncrementSeconds": 60,
        "maxFailureWaitSeconds": 900,
        "minimumQuickLoginWaitSeconds": 60,
        "permanentLockout": False
    }
    r = client.put(realm_url, json=update_payload, headers=headers)
    if r.status_code in [200, 201, 204]:
        print("Realm 'visionquery' brute-force policies updated successfully.")
    else:
        print(f"Failed to update realm brute force policies: {r.status_code} - {r.text}")
        return False
            
    # 3. Create Clients
    clients_url = f"{KEYCLOAK_URL}/admin/realms/visionquery/clients"
    clients = [
        {
            "clientId": "visionquery-frontend",
            "name": "Vision Query Frontend",
            "enabled": True,
            "publicClient": True,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "redirectUris": [
                "http://localhost:3000/*", "http://127.0.0.1:3000/*",
                "http://localhost:3001/*", "http://127.0.0.1:3001/*",
                "http://localhost:3002/*", "http://127.0.0.1:3002/*"
            ],
            "webOrigins": [
                "http://localhost:3000", "http://127.0.0.1:3000",
                "http://localhost:3001", "http://127.0.0.1:3001",
                "http://localhost:3002", "http://127.0.0.1:3002"
            ],
            "attributes": {
                "pkce.code.challenge.method": "S256"
            }
        },
        {
            "clientId": "visionquery-api",
            "name": "Vision Query API",
            "enabled": True,
            "publicClient": False,
            "secret": "supersecretkeycloakclientsecret",
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "redirectUris": ["http://localhost:8000/*"]
        }
    ]
    for client_payload in clients:
        r = client.post(clients_url, json=client_payload, headers=headers)
        if r.status_code in [201, 409]:
            print(f"Client '{client_payload['clientId']}' configured.")
        else:
            print(f"Failed to create client '{client_payload['clientId']}': {r.status_code} - {r.text}")
            
    # 4. Create Roles
    roles_url = f"{KEYCLOAK_URL}/admin/realms/visionquery/roles"
    roles = [
        {"name": "super_admin", "description": "Super administrator with global system access"},
        {"name": "org_admin", "description": "Organization administrator with tenant-wide access"},
        {"name": "operator", "description": "Operator role with limited camera access"},
        {"name": "analyst", "description": "Analyst role for running queries and exporting video"},
        {"name": "viewer", "description": "Viewer role with read-only access"}
    ]
    for role_payload in roles:
        r = client.post(roles_url, json=role_payload, headers=headers)
        if r.status_code in [201, 409]:
            print(f"Role '{role_payload['name']}' configured.")
        else:
            print(f"Failed to create role '{role_payload['name']}': {r.status_code} - {r.text}")
            
    # 5. Create Client Scopes
    scopes_url = f"{KEYCLOAK_URL}/admin/realms/visionquery/client-scopes"
    scopes = [
        "camera:read",
        "camera:write",
        "video:export",
        "alert:manage",
        "query:execute",
        "system:admin"
    ]
    for scope in scopes:
        scope_payload = {
            "name": scope,
            "protocol": "openid-connect",
            "attributes": {
                "include.in.token.scope": "true"
            }
        }
        r = client.post(scopes_url, json=scope_payload, headers=headers)
        if r.status_code in [201, 409]:
            print(f"Scope '{scope}' configured.")
        else:
            print(f"Failed to create scope '{scope}': {r.status_code} - {r.text}")
            
    print("Keycloak realm 'visionquery' configuration setup completed.")
    return True

if __name__ == "__main__":
    success = setup_keycloak()
    sys.exit(0 if success else 1)
