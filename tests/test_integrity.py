import pytest
from sqlalchemy.exc import IntegrityError

from shipgate.models import Project, Release
from tests.conftest import auth, project, release


def test_cross_tenant_fk_rejected_at_database_boundary(identities):
    e = identities
    with pytest.raises(IntegrityError):
        with e["factory"].begin() as db:
            foreign_project = Project(
                tenant_id=e["outsider_db"].tenant_id,
                slug="outsider-project", description="Foreign project",
            )
            db.add(foreign_project)
            db.flush()
            db.add(Release(
                tenant_id=e["operator_db"].tenant_id,
                project_id=foreign_project.id,
                created_by=e["operator_db"].id,
                environment="production", artifact_sha256="a" * 64,
                risk="high", description="This must fail due to cross-tenant FK",
                required_approvals=2, status="draft", version=1,
            ))
            db.flush()


def test_no_user_supplied_fields_or_invalid_digest(identities):
    e = identities
    p = project(e)
    body = {
        "project_id": p, "environment": "production", "risk": "low",
        "artifact_sha256": "a" * 64, "description": "Safe release request with known digest",
        "tenant_id": e["outsider_db"].tenant_id,
    }
    c = e["client"]
    headers = {**auth(e["operator"]), "Idempotency-Key": "irrelevant123"}
    response = c.post("/v1/releases", headers=headers, json=body)
    assert response.status_code == 422
    body.pop("tenant_id")
    body["artifact_sha256"] = "NOT_A_SHA"
    assert c.post("/v1/releases", headers=headers, json=body).status_code == 422
    body["artifact_sha256"] = "a" * 64
    assert c.post("/v1/releases", headers={"X-API-Key": e["operator"]},
                  json=body).status_code == 422


def test_only_release_author_or_admin_can_cancel(identities):
    e = identities
    item = release(e, project(e), idem="author-only-001")
    created = e["client"].post("/v1/keys", headers=auth(e["admin"]),
                                json={"label": "other-operator", "role": "operator"}).json()
    response = e["client"].post(
        f"/v1/releases/{item['id']}/cancel",
        headers=auth(created["key"]), json={"expected_version": 1},
    )
    assert response.status_code == 403
    assert e["client"].post(f"/v1/releases/{item['id']}/cancel",
                            headers=auth(e["admin"]),
                            json={"expected_version": 1}).status_code == 200
