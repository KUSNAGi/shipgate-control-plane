# Contributing to ShipGate

The project owner controls source distribution. There is no blanket license grant yet.
Contributions should be reviewed before they are pushed publicly.

## Development loop

1. Fork or branch from `main` after ensuring no secrets or customer data are present.
2. Run `pip install -e '.[dev]'` in a virtual environment.
3. Implement a focused improvement with an acceptance test and threat-model update.
4. Run `pytest -q --cov=shipgate`, `ruff check .`, and `alembic upgrade head` on a fresh database.
5. For changes affecting transactions or row locks, run against PostgreSQL as well.
6. Open a PR describing behavior, test evidence, migration impact and rollback plan.

Before merging, verify every claim of production readiness with an actual environment
and preserve approval separation of duties and tenant isolation.
