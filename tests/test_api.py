from tests.conftest import auth, project, release


def test_production_high_risk_requires_two_independent_approvals(identities):
    e = identities
    c = e["client"]
    p = project(e)
    item = release(e, p)
    assert item["status"] == "draft" and item["required_approvals"] == 2
    uid = item["id"]

    response = c.post(f"/v1/releases/{uid}/submit", json={"expected_version": 1},
                      headers=auth(e["operator"]))
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["version"] == 2

    self_review = c.post(
        f"/v1/releases/{uid}/reviews",
        json={"expected_version": 2, "decision": "approve"},
        headers=auth(e["operator"]),
    )
    assert self_review.status_code == 403

    first = c.post(
        f"/v1/releases/{uid}/reviews",
        json={"expected_version": 2, "decision": "approve", "note": "SAST passed"},
        headers=auth(e["reviewer_a"]),
    )
    assert first.status_code == 200, first.text
    assert first.json()["approval_count"] == 1
    assert first.json()["status"] == "submitted"

    duplicate = c.post(
        f"/v1/releases/{uid}/reviews",
        json={"expected_version": 3, "decision": "approve"},
        headers=auth(e["reviewer_a"]),
    )
    assert duplicate.status_code == 409

    second = c.post(
        f"/v1/releases/{uid}/reviews",
        json={"expected_version": 3, "decision": "approve"},
        headers=auth(e["reviewer_b"]),
    )
    assert second.status_code == 200
    assert second.json()["status"] == "approved"
    assert second.json()["approval_count"] == 2

    blocked = c.post(
        f"/v1/releases/{uid}/complete", headers=auth(e["operator"]),
        json={"expected_version": 4, "observed_artifact_sha256": "b" * 64,
              "evidence_url": "https://ci.example.org/run/42"},
    )
    assert blocked.status_code == 409
    good = c.post(
        f"/v1/releases/{uid}/complete", headers=auth(e["operator"]),
        json={"expected_version": 4, "observed_artifact_sha256": "a" * 64,
              "evidence_url": "https://ci.example.org/run/42"},
    )
    assert good.status_code == 200 and good.json()["status"] == "completed"
    assert good.json()["version"] == 5
    assert c.get("/v1/audit/verify", headers=auth(e["auditor"])).json()["valid"]


def test_staging_low_risk_zero_approvals(identities):
    e = identities
    item = release(e, project(e), environment="staging", risk="low")
    result = e["client"].post(
        f"/v1/releases/{item['id']}/submit", json={"expected_version": 1},
        headers=auth(e["operator"]),
    )
    assert result.status_code == 200 and result.json()["status"] == "approved"


def test_unauthorized_key_tenant_isolation_and_input_validation(identities):
    e = identities
    client = e["client"]
    p = project(e)
    r = release(e, p)
    assert client.get("/v1/projects").status_code == 401
    assert client.get("/v1/projects", headers={"X-API-Key": "sg_bad_invalid"}).status_code == 401
    assert client.get("/v1/projects", headers=auth(e["outsider"])).json() == []
    assert client.get(f"/v1/releases/{r['id']}", headers=auth(e["outsider"])).status_code == 404
    assert client.post(
        "/v1/releases", headers={**auth(e["outsider"]), "Idempotency-Key": "other-123456"},
        json={"project_id": p, "environment": "production", "risk": "low",
              "artifact_sha256": "a" * 64, "description": "Cannot access foreign project."},
    ).status_code == 404
    assert client.post(
        "/v1/projects", headers=auth(e["operator"]),
        json={"slug": "not-allowed", "description": "nope"},
    ).status_code == 403
    assert client.post(
        "/v1/projects", headers=auth(e["admin"]),
        json={"slug": "INVALID SLUG"},
    ).status_code == 422
    assert client.get("/v1/audit/events", headers=auth(e["operator"])).status_code == 403
    assert client.get("/v1/audit/events", headers=auth(e["outsider"])).json() == []


def test_idempotency_replay_and_payload_conflict(identities):
    e = identities
    client = e["client"]
    p = project(e)
    first = release(e, p, idem="repeat-me-001")
    replay = client.post(
        "/v1/releases", headers={**auth(e["operator"]), "Idempotency-Key": "repeat-me-001"},
        json={"project_id": p, "environment": "production", "risk": "high",
              "artifact_sha256": "a" * 64,
              "description": "Deploy build with security and reliability improvements"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert first["id"] == replay.json()["id"]
    assert first["version"] == replay.json()["version"]
    assert len(client.get("/v1/releases", headers=auth(e["operator"])).json()) == 1
    changed = client.post(
        "/v1/releases", headers={**auth(e["operator"]), "Idempotency-Key": "repeat-me-001"},
        json={"project_id": p, "environment": "staging", "risk": "high",
              "artifact_sha256": "a" * 64, "description": "different staged release content"},
    )
    assert changed.status_code == 409
    events = client.get("/v1/audit/events", headers=auth(e["admin"])).json()
    assert len([x for x in events if x["action"] == "release.created"]) == 1
    fresh = client.post(
        "/v1/releases", headers={**auth(e["operator"]), "Idempotency-Key": "fresh-key-002"},
        json={"project_id": p, "environment": "staging", "risk": "low",
              "artifact_sha256": "b" * 64,
              "description": "Separate deployment with a new request key"},
    )
    assert fresh.status_code == 201, fresh.text
    assert fresh.headers["Idempotency-Replayed"] == "false"
    assert fresh.json()["id"] != first["id"]


def test_conflicts_and_rejection(identities):
    e = identities
    client = e["client"]
    p = project(e)
    r = release(e, p)
    u = r["id"]
    assert client.post(f"/v1/releases/{u}/submit", headers=auth(e["operator"]),
                       json={"expected_version": 2}).status_code == 409
    assert client.post(f"/v1/releases/{u}/complete", headers=auth(e["operator"]),
                       json={"expected_version": 1, "observed_artifact_sha256": "a" * 64,
                             "evidence_url": "https://example.org/ci/1"}).status_code == 409
    client.post(f"/v1/releases/{u}/submit", headers=auth(e["operator"]),
                json={"expected_version": 1})
    rejected = client.post(f"/v1/releases/{u}/reviews", headers=auth(e["reviewer_a"]),
                           json={"expected_version": 2, "decision": "reject",
                                 "note": "Artifact missing SLSA attestation"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.post(f"/v1/releases/{u}/cancel", headers=auth(e["operator"]),
                       json={"expected_version": 3}).status_code == 409


def test_key_issue_and_revocation(identities):
    e = identities
    client = e["client"]
    assert client.post("/v1/keys", headers=auth(e["operator"]),
                       json={"label": "invalid key", "role": "admin"}).status_code == 403
    created = client.post("/v1/keys", headers=auth(e["admin"]),
                          json={"label": "new approver", "role": "approver"})
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("sg_")
    assert client.get("/v1/me", headers=auth(body["key"])).json()["role"] == "approver"
    assert client.post(f"/v1/keys/{body['id']}/revoke", headers=auth(e["admin"])).status_code == 200
    assert client.get("/v1/me", headers=auth(body["key"])).status_code == 401
    assert client.post(f"/v1/keys/{e['admin_db'].id}/revoke",
                       headers=auth(e["admin"])).status_code == 409
    listed = client.get("/v1/keys", headers=auth(e["auditor"]))
    assert listed.status_code == 200
    assert all("secret_hash" not in row and "key" not in row for row in listed.json())


def test_payload_body_limit_health_and_cancellation(identities):
    e = identities
    client = e["client"]
    assert client.get("/health/live").json() == {"status": "live"}
    assert client.get("/health/ready").status_code == 200
    blocked = client.post("/v1/projects", headers=auth(e["admin"]),
                          content=b"X" * 40_000)
    assert blocked.status_code == 413
    r = release(e, project(e))
    result = client.post(f"/v1/releases/{r['id']}/cancel", headers=auth(e["operator"]),
                         json={"expected_version": 1})
    assert result.status_code == 200 and result.json()["status"] == "cancelled"
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["X-Request-ID"]


def test_environment_rejects_unprotected_production_settings():
    from shipgate.config import Settings
    import pytest

    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="production").validate_for_serving()
