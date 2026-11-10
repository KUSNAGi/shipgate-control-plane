# Real engineering backlog

These are proposed milestones for continuing a useful release-governance service, not
features already delivered.

## P1: Identity-bound human approvals

- OpenID Connect device/browser sign-in with organization membership and MFA claim checks.
- Bind approvals to independent human subjects rather than API credential IDs.
- Permission scopes by environment/project and separation-of-duties policy tests.
- v0.2 delivers expiring API keys and atomic administrative rotation; service keys are still
  not proof of distinct human identity.

## P1: Verified deployment evidence

- GitHub Actions / GitLab CI OIDC verifier for workflow identity and run provenance.
- Sigstore / SLSA artifact provenance validation (digest, builder identity, workflow ref).
- Callback replay defense, strict allowlisted signer keys, and immutable evidence objects.

## P1: Tenant-grade traffic controls

- Gateway quotas and app-side shared-store rate control; key rotation and expiration.
- Exportable signed audit checkpoints to WORM object storage.
- Cursor-based pagination for high-volume projects and audit stream.

## P2: Operator experience

- A small accessible console with release timeline, decision history and evidence viewer.
- Policy-as-code configuration with signed policy versions and evaluation trace.
- Notification outbox and idempotent webhook/event delivery for decisions.

## P2: Operations

- OpenTelemetry traces and metrics, dashboards, DB retention partitioning.
- Stress tests for approval contention, crashes, duplicate creates and replica rollouts.
- Reliable HA deployment, backup restoration drill, dependency locking/SBOM.

Each feature should ship with tests, an ADR, documented migration impact and a
representative integration scenario; no mock status should be described as production-ready.
