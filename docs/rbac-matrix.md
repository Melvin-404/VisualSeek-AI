# Role-Based Access Control (RBAC) Matrix

This document defines the roles, permissions, and scoping rules within the Vision Query enterprise platform.

## Permissions Definitions

| Scope/Permission | Description |
| :--- | :--- |
| `camera:read` | Read camera configuration metadata and stream video. |
| `camera:write` | Create, update, or delete cameras. |
| `video:export` | Export video clips from cameras. |
| `alert:manage` | Create, acknowledge, and resolve alerts/events. |
| `query:execute` | Run natural language search queries against vector embeddings. |
| `system:admin` | Global administrative tasks (e.g. system logs, global configs). |

---

## Role to Permission Mapping

The table below maps each system role to its set of permissions:

| Permission / Scope | `super_admin` | `org_admin` | `operator` | `analyst` | `viewer` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `camera:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `camera:write` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `video:export` | ✅ | ✅ | ❌ | ✅ | ❌ |
| `alert:manage` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `query:execute` | ✅ | ✅ | ❌ | ✅ | ❌ |
| `system:admin` | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## Data Scoping Rules

In addition to permission scopes, Vision Query enforces logical tenant isolation and camera-level access restrictions:

### 1. Tenant Isolation (Multitenancy)
- All requests are isolated by the tenant ID claim (present in the JWT token or resolved from the service API key).
- A user or service belonging to organization `A` **cannot** read or write cameras, video segments, detected objects, or events belonging to organization `B` (returns `403 Forbidden`).
- The `super_admin` role has global access across all tenants.

### 2. Camera-Level Scoping for Operators
- **Operator** role users are restricted to **assigned cameras** only.
- Access to camera streams, configurations, and associated alerts is blocked unless a mapping entry exists in the `camera_assignments` table matching the operator's user UUID.
- Admin, Analyst, and Viewer roles automatically have access to all cameras within their tenant.
