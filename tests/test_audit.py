from sqlalchemy import select

from shipgate.models import AuditEvent
from tests.conftest import auth, project, release


def test_audit_chain_detects_rewritten_history(identities):
    e = identities
    project_id = project(e)
    release(e, project_id)
    response = e["client"].get("/v1/audit/verify", headers=auth(e["admin"]))
    assert response.json()["valid"] is True
    with e["factory"].begin() as session:
        first = session.scalar(select(AuditEvent).where(
            AuditEvent.tenant_id == e["admin_db"].tenant_id,
        ).order_by(AuditEvent.sequence))
        first.payload = {"slug": "hacked"}
    response = e["client"].get("/v1/audit/verify", headers=auth(e["admin"]))
    assert response.status_code == 200 and response.json()["valid"] is False


def test_audit_pagination_no_cross_tenant_leak(identities):
    e = identities
    release(e, project(e))
    first = e["client"].get("/v1/audit/events?limit=1", headers=auth(e["admin"]))
    assert len(first.json()) == 1
    other = e["client"].get("/v1/audit/events?after=0", headers=auth(e["outsider"]))
    assert other.json() == []
