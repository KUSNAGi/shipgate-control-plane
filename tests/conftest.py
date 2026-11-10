import pytest
from pathlib import Path
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from shipgate.api import create_app
from shipgate.config import Settings
from shipgate.db import build_engine
from shipgate.models import ApiKey, AuditHead, Tenant
from shipgate.security import new_api_key


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.sqlite3'}"
    monkeypatch.setenv("SHIPGATE_DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(alembic_config, "head")
    engine = build_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(environment="test", database_url=url)
    with TestClient(create_app(factory, settings)) as client:
        def identity(tenant: str, role: str, label: str) -> tuple[str, ApiKey]:
            with factory.begin() as db:
                tenant_obj = db.query(Tenant).filter(Tenant.slug == tenant).one_or_none()
                if tenant_obj is None:
                    tenant_obj = Tenant(slug=tenant)
                    db.add(tenant_obj)
                    db.flush()
                    db.add(AuditHead(tenant_id=tenant_obj.id, sequence=0, last_hash="0" * 64))
                raw, prefix, digest = new_api_key()
                record = ApiKey(
                    tenant_id=tenant_obj.id, prefix=prefix, secret_hash=digest,
                    label=label, role=role,
                )
                db.add(record)
                db.flush()
                return raw, record

        yield client, factory, identity
    engine.dispose()


@pytest.fixture
def identities(test_env):
    client, factory, make = test_env
    operator, operator_db = make("acme", "operator", "release-engineer")
    admin, admin_db = make("acme", "admin", "owner")
    approver_a, approver_a_db = make("acme", "approver", "sec-reviewer")
    approver_b, approver_b_db = make("acme", "approver", "sre-reviewer")
    auditor, auditor_db = make("acme", "auditor", "compliance")
    outsider, outsider_db = make("other", "admin", "other-owner")
    return {
        "client": client, "factory": factory,
        "operator": operator, "operator_db": operator_db,
        "admin": admin, "admin_db": admin_db,
        "reviewer_a": approver_a, "reviewer_a_db": approver_a_db,
        "reviewer_b": approver_b, "reviewer_b_db": approver_b_db,
        "auditor": auditor, "auditor_db": auditor_db,
        "outsider": outsider, "outsider_db": outsider_db,
    }


def auth(token: str):
    return {"X-API-Key": token}


def project(env, slug="payments-api"):
    client = env["client"]
    response = client.post(
        "/v1/projects", headers=auth(env["admin"]),
        json={"slug": slug, "description": "Deployable payment gateway"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def release(env, project_id, *, idem="one-release-0001", environment="production", risk="high"):
    client = env["client"]
    sha = "a" * 64
    response = client.post(
        "/v1/releases", headers={**auth(env["operator"]), "Idempotency-Key": idem},
        json={"project_id": project_id, "environment": environment,
              "artifact_sha256": sha, "risk": risk,
              "description": "Deploy build with security and reliability improvements"},
    )
    assert response.status_code == 201, response.text
    return response.json()
