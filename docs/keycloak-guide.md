# Keycloak SSO Integration Guide

This guide details Keycloak OIDC/SSO integration, security controls, and realm provisioning using Terraform IaC.

## Keycloak Architecture

```
                                +-------------------+
                                |     Keycloak      |
                                |      (OIDC)       |
                                +---------+---------+
                                          |
                        1. Authenticate   |  2. RS256 JWT
                                          v
+-------------------+           +---------+---------+
|    Web Client     +---------->+    FastAPI App    |
|      (PKCE)       |  3. Call  |   (JWKS Cache)    |
+-------------------+           +-------------------+
```

---

## 1. Keycloak Security Controls

### Brute Force Lockout Policy
To comply with security requirements, the `visionquery` realm locks out accounts after 5 failed authentication attempts:
- **Max Login Failures**: `5`
- **Wait Increment**: `60 seconds`
- **Max Failure Wait**: `15 minutes` (900 seconds)
- **Failure Reset Time**: `12 hours`

This policy is defined as code in `infra/terraform/keycloak/main.tf` under the `brute_force_detection` block.

### MFA (Multi-Factor Authentication) Enforcement
Administrators (`super_admin` and `org_admin` roles) must be configured to enforce MFA on login.
To configure this:
1. Navigate to Keycloak Admin Console -> **Authentication** -> **Required Actions**.
2. Set **Configure OTP** as a default required action for administrators.
3. Upon login, admins will be prompted to register an authenticator app (Google Authenticator, FreeOTP).

---

## 2. Terraform Realm Provisioning

### Prerequisites
- Keycloak container running on port `8080`.
- Terraform installed on the host.

### Step 1: Initialize Terraform
Navigate to the terraform folder and initialize:
```bash
cd infra/terraform/keycloak
terraform init
```

### Step 2: Apply Configuration
Apply the code to provision the `visionquery` realm:
```bash
terraform apply
```
This defines clients (`visionquery-frontend` and `visionquery-api`), roles (`super_admin`, `org_admin`, etc.), and lockout settings.
