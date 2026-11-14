# Changelog

## 0.3.0 · 2026-11-14

- Introduced project-specific, versioned approval quorum policies for each environment/risk pair.
- Enforced platform safety floors and administrator-only policy mutations.
- Snapshotted effective policy provenance and quorum on newly created releases.
- Serialized policy writes and release creation through PostgreSQL project row locks.
- Logged policy updates into tenant-scoped hash-linked audit records.
- Added API, multi-tenant, reviewer-quorum, policy-snapshot, and conflict regression tests.
- Added ADR-0003 and interview walkthrough documenting trade-offs and incomplete validation.
- Integrated upstream fixes from #3 (validated evidence URL) and #4 (idempotent-replay 200/201).

**Validation:** 33 SQLite tests passing, 1 PostgreSQL test skipped, 92% coverage on Python 3.13.
Production readiness is blocked until PostgreSQL/Compose CI and staging checks pass.

## 0.2.0 · 2026-11-10

- Added expiring API keys, atomic rotation/revocation, and CI PostgreSQL/Compose jobs.

## 0.1.0 · 2026-11-10

- Initial tenant-isolated release approval API, audit chain, migrations, and test suite.
