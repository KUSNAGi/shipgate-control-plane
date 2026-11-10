"""API-key TTL and atomic rotation acceptance coverage."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from shipgate.models import ApiKey
from tests.conftest import auth


def test_new_keys_have_bounded_expiration_and_no_secret_exposure(identities):
    e = identities
    client = e["client"]
    response = client.post("/v1/keys", headers=auth(e["admin"]),
                           json={"label": "short lived", "role": "operator", "ttl_hours": 2})
    assert response.status_code == 201, response.text
    issued = response.json()
    deadline = datetime.fromisoformat(issued["expires_at"])
    assert timedelta(minutes=119) < deadline - datetime.now(timezone.utc) < timedelta(hours=2)
    assert client.get("/v1/me", headers=auth(issued["key"])).status_code == 200
    listed = client.get("/v1/keys", headers=auth(e["admin"])).json()
    saved = next(x for x in listed if x["id"] == issued["id"])
    assert datetime.fromisoformat(saved["expires_at"]).replace(tzinfo=timezone.utc) == (
        datetime.fromisoformat(issued["expires_at"]).replace(tzinfo=timezone.utc)
    )
    assert "key" not in saved and "secret_hash" not in saved
    for ttl in (0, -1, 2161, "not-an-integer"):
        assert client.post("/v1/keys", headers=auth(e["admin"]),
                           json={"label": "bad", "role": "auditor", "ttl_hours": ttl}).status_code == 422


def test_expired_key_fails_closed(identities):
    e = identities
    client = e["client"]
    with e["factory"].begin() as db:
        key = db.get(ApiKey, e["reviewer_a_db"].id)
        key.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert client.get("/v1/me", headers=auth(e["reviewer_a"])).status_code == 401
    assert client.get("/v1/me", headers=auth(e["admin"])).status_code == 200


def test_atomic_rotation_revokes_old_token_and_preserves_role(identities):
    e = identities
    client = e["client"]
    response = client.post(f"/v1/keys/{e['reviewer_a_db'].id}/rotate",
                           headers=auth(e["admin"]), json={"ttl_hours": 36})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["id"] != e["reviewer_a_db"].id
    assert result["role"] == "approver" and result["label"] == "sec-reviewer"
    assert client.get("/v1/me", headers=auth(e["reviewer_a"])).status_code == 401
    assert client.get("/v1/me", headers=auth(result["key"])).json()["role"] == "approver"
    assert client.post(f"/v1/keys/{e['reviewer_a_db'].id}/rotate",
                       headers=auth(e["admin"]), json={}).status_code == 409
    assert client.post(f"/v1/keys/{e['reviewer_b_db'].id}/rotate",
                       headers=auth(e["operator"]), json={}).status_code == 403
    assert client.post(f"/v1/keys/{e['outsider_db'].id}/rotate",
                       headers=auth(e["admin"]), json={}).status_code == 404
    events = client.get("/v1/audit/events", headers=auth(e["auditor"])).json()
    assert any(x["action"] == "key.rotated" for x in events)
    assert client.get("/v1/audit/verify", headers=auth(e["auditor"])).json()["valid"]


def test_self_rotation_preserves_admin_access_with_new_key(identities):
    e = identities
    client = e["client"]
    created = client.post(f"/v1/keys/{e['admin_db'].id}/rotate",
                          headers=auth(e["admin"]), json={})
    assert created.status_code == 201, created.text
    assert client.get("/v1/me", headers=auth(e["admin"])).status_code == 401
    assert client.get("/v1/me", headers=auth(created.json()["key"])).json()["role"] == "admin"
    with e["factory"].begin() as db:
        keys = db.scalars(select(ApiKey).where(ApiKey.tenant_id == e["admin_db"].tenant_id,
                                               ApiKey.role == "admin")).all()
        assert sum(not k.revoked for k in keys) == 1
