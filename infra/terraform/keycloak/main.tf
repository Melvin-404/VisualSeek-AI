resource "keycloak_realm" "visionquery" {
  realm             = "visionquery"
  enabled           = true
  display_name      = "VisualSeek AI"
  display_name_html = "<b>VisualSeek AI</b>"

  login_theme = "keycloak"

  # Account Lockout Policy: Lock out after 5 failures
  security_defences {
    brute_force_detection {
      permanent_lockout  = false
      max_login_failures = 5
      wait_increment    = "60s"
      max_failure_wait   = "900s"
      failure_reset_time = "43200s" # 12 hours
    }
  }
}

# Roles Definition
resource "keycloak_role" "super_admin" {
  realm_id    = keycloak_realm.visionquery.id
  name        = "super_admin"
  description = "Super administrator with global system access"
}

resource "keycloak_role" "org_admin" {
  realm_id    = keycloak_realm.visionquery.id
  name        = "org_admin"
  description = "Organization administrator with tenant-wide access"
}

resource "keycloak_role" "operator" {
  realm_id    = keycloak_realm.visionquery.id
  name        = "operator"
  description = "Operator role with limited camera access"
}

resource "keycloak_role" "analyst" {
  realm_id    = keycloak_realm.visionquery.id
  name        = "analyst"
  description = "Analyst role for running queries and exporting video"
}

resource "keycloak_role" "viewer" {
  realm_id    = keycloak_realm.visionquery.id
  name        = "viewer"
  description = "Viewer role with read-only access"
}

# Client Scopes Definition
variable "scopes" {
  type = list(string)
  default = [
    "camera:read",
    "camera:write",
    "video:export",
    "alert:manage",
    "query:execute",
    "system:admin"
  ]
}

resource "keycloak_openid_client_scope" "scopes" {
  for_each = toset(var.scopes)
  realm_id = keycloak_realm.visionquery.id
  name     = each.value
}

# Frontend OIDC Client (Public Client with PKCE)
resource "keycloak_openid_client" "frontend" {
  realm_id              = keycloak_realm.visionquery.id
  client_id             = "visionquery-frontend"
  name                  = "VisualSeek AI Frontend"
  enabled               = true
  access_type           = "PUBLIC"
  standard_flow_enabled = true
  implicit_flow_enabled = false
  direct_access_grants_enabled = true
  pkce_code_challenge_method = "S256"

  valid_redirect_uris = [
    "http://localhost:3000/*",
    "http://127.0.0.1:3000/*"
  ]

  web_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
  ]
}

# API OIDC Client (Confidential Client)
resource "keycloak_openid_client" "api" {
  realm_id                     = keycloak_realm.visionquery.id
  client_id                    = "visionquery-api"
  name                         = "VisualSeek AI API"
  enabled                      = true
  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = true
  direct_access_grants_enabled = true

  valid_redirect_uris = [
    "http://localhost:8000/*"
  ]
}
