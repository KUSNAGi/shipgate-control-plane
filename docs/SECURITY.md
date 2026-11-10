# Security model, threat assumptions and limitations

## Current controls

- API access requires random 36-byte URL-safe secrets, keyed by an indexed random prefix.
  Each secret is stored as SHA-256 only. Constant-time digest comparison is used.
- Roles: admins create projects/keys, operators propose & submit releases, approvers
  review, auditors inspect the audit chain. Authors cannot review their own releases.
- All mutable resources have tenant-constrained queries; composite database keys enforce
  critical tenant integrity even against application mistakes.
- HTTP bodies are capped (default 32 KiB) before parsing; reverse proxies must enforce the
  same or a smaller limit. Unknown JSON fields and invalid digest formats are rejected.
- No permissive CORS policy. Trusted HTTP hosts must be explicitly set in production.
- PostgreSQL serializes state transitions and audit append operations with row locks;
  per-idempotency-key advisory locks prevent duplicate concurrent release creation.
- The service does **not** fetch evidence URLs. HTTPS-only values prevent accidental
  insecure references; no claims are made about the referenced site's authenticity.
- Docker runs as UID 10001, with a read-only filesystem, dropped Linux capabilities,
  no-new-privileges, and no exposed DB port in the sample Compose topology.
- No user credentials, proprietary source code, personal identifiers, or live secrets are
  included in this repository.

## Limitations before internet-facing production

1. **No rate limiter built into the API.** Enforce request/IP/key quotas at the gateway;
   avoid calling the service without a reverse proxy.
2. **API key identity is not human identity.** An admin can issue multiple approver keys,
   and one person can possess them. Enforce identity-bound SSO and independent approval
   policy before high-assurance deployments.
3. **The audit head is in the same DB as events.** Anchor signed hashes externally in
   append-only storage for protection against database administrator tampering.
4. **Actual deployment evidence is not independently verified.** CI/CD systems should
   sign artifact attestations and authenticate callbacks; ShipGate only records the
   provided evidence URL and digest match in v0.1.
5. **No native TLS server, network perimeter, or secret vault.** Use TLS termination,
   a private DB, secret manager, rotation/backup plan, and managed ingress controls.
6. **Credentials can be disclosed by operators.** The CLI prints the new bootstrap key
   once; run it in a trusted terminal without session capture. A leaked key must be
   revoked by another admin key.
7. **No security/pentest or load-test certification.** These are required before a real
   production SLO, as are PostgreSQL integration validation and dependency review.
8. **Dependencies in pyproject use bounded ranges, not a generated hash-pinned lock.**
   Freeze and review a lockfile/SBOM for each release and scan image dependencies.

## Safe disclosure

Use GitHub Security Advisories or a private maintainer contact. Never disclose live
keys, production logs, real deployment URLs with embedded tokens, or customer data in an issue.
