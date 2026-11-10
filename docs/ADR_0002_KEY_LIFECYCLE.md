# ADR-0002: Bounded API-key lifetime and atomic rotation

**Status:** accepted for v0.2.0 (10 November 2026)

## Decision

- New API keys default to **30 days (720 hours)**; caller may request 1–2160 hours.
- Previously issued API keys remain without an expiry (`NULL`) to avoid a breaking migration.
  Rotate those keys before internet deployment; inventory them via `GET /v1/keys`.
- Authentication rejects expired keys with the same generic 401 as invalid/revoked secrets.
- `POST /v1/keys/{key_id}/rotate` is admin-only, locks the old key row on PostgreSQL,
  issues a new key with identical role/label, and revokes the old key in **one transaction**.
- The new plaintext secret appears only in the 201 response; audit logs contain IDs and the
  expiry timestamp, not a token or token digest.

## Tradeoffs and limitations

- API keys are **service identities**, not human identities. This does not establish
  two independent human approvers; SSO remains a future milestone.
- PostgreSQL row-lock serialization governs concurrent rotations. SQLite is only the
  single-process development backend and cannot replicate this guarantee.
- The endpoint cannot safely replay a one-time secret: lost rotate responses require
  an admin to issue another key and revoke the previous replacement.
- Token presentation over HTTPS and secure vault storage remain deployment requirements.

## Rollback

The migration only adds a nullable column. Downgrading drops expiration metadata and
**removes the expiry enforcement**; do not downgrade without revoking or rotating all
short-lived keys and a documented operator decision.
