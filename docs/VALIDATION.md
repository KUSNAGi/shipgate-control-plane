# Development verification record

Evaluation date: **2026-11-10** (Asia/Kolkata).

## Verified in the authoring environment

- Python: 3.13.5.
- Database: SQLite, schema created through the real Alembic migration.
- Command: `pytest -q` → **15 passed, 1 skipped**.
- Command: `pytest -q --cov=shipgate --cov-report=term-missing` → **90% overall coverage**
  at the time recorded (the source changed only for nonbehavioral hardening afterward;
  rerun for a fresh value).
- Command: `python -m compileall -q shipgate alembic tests` → passed.
- Alembic migration upgrade/downgrade/re-upgrade exercised in automated tests.
- YAML syntax of GitHub Actions and Compose files parsed successfully.
- No credentials or personal/proprietary content deliberately inserted.

## Not verified locally

- PostgreSQL integration (CI service and test are configured but local PostgreSQL was not available).
- Docker image and Compose service startup (Docker engine unavailable).
- Ruff static analysis (binary unavailable and network package installation disabled).
- Image/dependency vulnerability scans, load tests, operational monitoring and incident drills.
- Real deployment, HTTPS ingress, external audit anchoring, human-bound reviewer identity.

These are explicit gates to complete before claiming an operationally production-qualified
system. They do not block source review or further development, but must not be silently
represented as already passing.
