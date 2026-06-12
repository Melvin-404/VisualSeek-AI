# Service-to-Service API Key Rotation

This document outlines the security procedures, database storage, validation mechanism, and rotation instructions for service-to-service API keys.

## API Key Security Architecture
API keys enable external services (such as the AI pipeline) to authenticate without user interactive login.
- **Key Prefix**: All active API keys start with `vq_live_` to prevent accidental commits.
- **Hashing**: Raw keys are never stored in the database. Instead, they are hashed using **SHA-256** (`key_hash`).
- **Authorization**: Keys are bound to specific scopes (e.g. `['camera:read', 'query:execute']`) and an organization tenant ID.
- **Expiry**: All keys should have an expiration timestamp set (`expires_at`).

---

## 1. Key Generation Procedure

To generate a new key for a service:
1. Generate a secure random hex token (64 characters).
2. Format the API Key: `vq_live_<64-character-token>`.
3. Compute the SHA-256 hash of the full formatted key.
4. Insert the record into the `api_keys` database table:
   ```sql
   INSERT INTO api_keys (id, org_id, name, key_hash, scopes, is_active, expires_at)
   VALUES (
       gen_random_uuid(),
       '<tenant-org-uuid>',
       'AI Pipeline Service',
       '<sha256-hash-value>',
       '["camera:read", "query:execute"]'::jsonb,
       true,
       NOW() + INTERVAL '90 days'
   );
   ```

---

## 2. API Key Rotation Workflow

To rotate a service API key with zero downtime, use the **Double-Keying** strategy:

1. **Provision New Key**: Generate a new API key and insert its hash into `api_keys` (set expiration to 90 days). Keep the old key active.
2. **Update Service**: Deploy the new key to the client service (e.g., update environment variable `VISIONQUERY_API_KEY`).
3. **Verify Usage**: Check database audit logs to ensure traffic is successfully authenticating using the new key ID.
4. **Revoke Old Key**: Set `is_active = false` or delete the record for the old key in the `api_keys` table.
