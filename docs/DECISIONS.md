# Architecture decisions

## ADR-001: PostgreSQL as production authority

SQLite supports easy local evaluation but does not provide the required `SELECT FOR UPDATE`
and advisory-lock semantics. PostgreSQL is mandatory for concurrent production workers.
Database transactions are the consistency boundary; no cache is an authority for approvals.

## ADR-002: Explicit state machine, no workflow engine

Workflow transitions live in pure policy helpers and transactional service functions.
No Celery/Redis infrastructure is needed to authorize a release. This avoids a second
source of truth and is easier to test under contention.

## ADR-003: Hash-linked audit with explicit caveat

A hash chain makes retrospective rewriting detectable when a trusted head is available.
It is not cryptographic non-repudiation or protection from an all-powerful DB admin.
External anchoring remains a deliberate future milestone.

## ADR-004: No automatic deployment execution

The service controls release approval and records evidence; actual CI/CD tooling must
perform deployments. This keeps the initial attack surface small and avoids storing
cloud credentials or arbitrary shell commands in ShipGate.

## ADR-005: Separate identities for different duties

Admin, operator, approver, and auditor keys are scoped per tenant. Current separation
of duties is per API credential, not per verified human. Identity-bound SSO is required
before highly regulated use. The API exposes this limitation rather than claiming more.
