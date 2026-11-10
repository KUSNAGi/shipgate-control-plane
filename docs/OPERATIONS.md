# Operator runbook

## Provisioning

1. Start a PostgreSQL database on a private network and configure a least-privilege DB user.
2. Apply `alembic upgrade head` in a separate migration job.
3. Set `SHIPGATE_ENVIRONMENT=production`, a PostgreSQL URL from a secrets manager, and
   a JSON `SHIPGATE_TRUSTED_HOSTS` list matching the API's ingress hostname.
4. Run `shipgate bootstrap --tenant <slug>` once in an isolated terminal. Record the admin
   secret in a vault; only a SHA-256 digest is persisted.
5. Place the API behind TLS and the gateway's request size, IP/key rate and connection caps.
6. Confirm `/health/live`, `/health/ready` and tenant `/v1/audit/verify` using a dedicated
   auditor key; verify database backup and restore before accepting production traffic.

## Daily operation

- Validate the full release record before approval: author, environment, risk, digest,
  code review, and test evidence. Two distinct *credentials* are required for high-risk
  production releases; identity independence is an organizational policy in this version.
- Keep CI evidence and change notices outside the API as source-of-truth artifacts.
- On `409`, fetch the release again, inspect current version/status, then decide whether
  to retry. Never blindly increment a version or reapprove a revised release.
- On a lost create response, repeat the same `Idempotency-Key` and identical payload.
- On compromised key, revoke from an independent admin key via `POST /v1/keys/{id}/revoke`.

## Recovery and integrity

- Run `shipgate verify-audit --tenant <slug>` or call `/v1/audit/verify` as an auditor.
- Investigate any invalid chain as a potential integrity incident; do **not** rewrite
  events or silently reset the head. Preserve snapshots and independently anchored hashes.
- Use database point-in-time recovery for data loss. Reconcile all releases and audit
  heads against externally anchored hashes, not just `alembic_version`.
- Back up PostgreSQL, application configuration (excluding secrets), and archived CI
  evidence on a rehearsed retention schedule.

## Deployment qualification checklist

- [ ] Docker image built and scanned with locked dependencies / SBOM.
- [ ] Full SQLite suite and PostgreSQL integration suite pass.
- [ ] Static analysis, migration up/down and rollback plan reviewed.
- [ ] Production ingress TLS, trusted hosts, rate limits and WAF validated.
- [ ] Separate admin/approver/operator identities and secrets manager configured.
- [ ] CI evidence and digest attestations authenticated independently.
- [ ] Backup and restore tested; external audit hash anchor enabled.
- [ ] Observability, alerting, capacity, load and failure testing completed.
- [ ] Operators sign off on migration and rollback steps.

**Project v0.1 has not passed this entire checklist.**
