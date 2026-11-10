"""Real PostgreSQL smoke, executed in CI; skipped when no test database supplied."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from shipgate.api import create_app
from shipgate.config import Settings
from shipgate.db import build_engine
from shipgate.models import ApiKey, AuditHead, Tenant
from shipgate.security import new_api_key


@pytest.mark.skipif(not os.getenv("SHIPGATE_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
def test_migrations_and_release_on_real_postgres(monkeypatch):
    url = os.environ["SHIPGATE_TEST_POSTGRES_URL"]
    monkeypatch.setenv("SHIPGATE_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = build_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        tenant = Tenant(slug=f"ci-{uuid4().hex[:12]}")
        db.add(tenant)
        db.flush()
        db.add(AuditHead(tenant_id=tenant.id, sequence=0, last_hash="0" * 64))
        raw, prefix, digest = new_api_key()
        db.add(ApiKey(
            tenant_id=tenant.id, prefix=prefix, secret_hash=digest,
            label="ci-admin", role="admin",
        ))
    settings = Settings(
        environment="test", database_url=url,
        trusted_hosts=["localhost", "127.0.0.1", "testserver"],
    )
    with TestClient(create_app(factory, settings)) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200, response.text
        response = client.post(
            "/v1/projects", headers={"X-API-Key": raw},
            json={"slug": "release-check", "description": "CI workflow"},
        )
        assert response.status_code == 201, response.text
        response = client.get("/v1/audit/verify", headers={"X-API-Key": raw})
        assert response.json()["valid"] is True
    engine.dispose()
