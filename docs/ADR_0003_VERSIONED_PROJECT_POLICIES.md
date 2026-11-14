# ADR-0003: Versioned, tenant-scoped project approval policies

**Status:** Accepted · **Date:** 2026-11-14

## Context

A single fixed policy cannot reflect different risk tolerances across projects.
Changing requirements after a release is created can retroactively rewrite the
meaning of past approvals, which is unacceptable for an auditable control plane.

## Decision

- Keep immutable platform approval **floors**: production low/medium=1,
  production high=2, staging high=1, all others=0.
- Allow a tenant admin to create/update a `ProjectPolicy` keyed by
  `(tenant_id, project_id, environment, risk)` with quorum 0–5, always at
  or above the floor. Enforcement uses `max(baseline, configured)`.
- Use `expected_version` optimistic concurrency. A missing policy has version 0,
  first write version 1. Lock the containing Project row before reads/writes
  to serialize concurrent creates and writes under PostgreSQL.
- Persist `required_approvals`, `policy_source`, and `policy_version` on every
  release **at creation time**; subsequent project policy edits do not
  retroactively affect that release. Idempotent retries return that snapshot.
- Audit `policy.updated` with environment/risk/quorum/version, never any API key.
- Keep project policy reads available to any valid project tenant principal,
  writes restricted to admin role, and return 404 for foreign projects.

## Alternatives

- **Dynamic policy evaluation on submission:** rejected because it lets a later
  administrator silently change an existing release's required quorum.
- **One policy per tenant:** rejected because requirements differ by project.
- **Policy text as executable code:** deferred until policies have a sandboxed,
  signed and independently reviewed rules engine.

## Consequences and future work

- Admins can only tighten floors, not create a zero-approval production bypass.
- The API supports 5 reviewers maximum per rule; policies beyond this need an
  explicit schema/API change with test coverage.
- PostgreSQL must be exercised before production qualification.
- Only key identities are distinct; future enterprise SSO work should bind
  approvals to human/service identities across key rotation.
- Policy rows are mutable but historical release snapshots plus audit events
  preserve the effect and revision used. Independent WORM anchoring remains needed
  for privileged database adversaries.
