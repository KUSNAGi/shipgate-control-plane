# ShipGate coding assistant contract

ShipGate is a real release governance and evidence-recording service, not a tutorial
app. Make changes that improve its correctness, operability, security, or usability.

## Read first

- `README.md` for the current feature boundary.
- `docs/ARCHITECTURE.md` and `docs/SECURITY.md` for trust and threat models.
- `docs/DECISIONS.md` for deliberate trade-offs.
- `docs/ROADMAP.md` for planned, not implemented, work.

## Repository rules

- **Never** import or copy code, prompts, credentials, or architecture documents from
  other private projects. This is independently implemented.
- Preserve tenant isolation in ORM queries *and* database integrity constraints.
- Author/approver separation must remain enforced. A credential is not a human identity;
  do not claim otherwise without implementing identity-bound authorization.
- Treat PostgreSQL as the production concurrency authority, SQLite as dev-only.
- Keep release mutation, version checking, audit append and idempotency in one transaction.
- Only describe a feature as functional when implementation and passing tests support it.
- Do not introduce arbitrary outbound network fetches, shell execution, or secret logging.
- New features need positive, negative, cross-tenant and concurrent/race tests when relevant.
- Migrations accompany schema changes, with downgrade strategy and rollback notes.
- Before submitting: run pytest, Ruff, migration smoke, and security-impact review.

## Suitable first contributions

1. Identity-bound approvals via OIDC with testable organizational role policy.
2. Provenance verification for GitHub Actions OIDC and attested artifact digests.
3. External tamper-evident hash checkpoint export, verified before replay.
4. PostgreSQL contention tests for many simultaneous release approvals.

Explain trade-offs, list operational dependencies, and avoid fabricating production results.
