"""Versioned project-policy overrides, immutable release snapshots, and isolation."""

from tests.conftest import auth, project, release


def policy_url(project_id: str, environment="staging", risk="low"):
    return f"/v1/projects/{project_id}/policies/{environment}/{risk}"


def set_policy(env, project_id, approvals, version=0, *, token=None, environment="staging", risk="low"):
    return env["client"].put(
        policy_url(project_id, environment, risk),
        headers=auth(token or env["admin"]),
        json={"min_approvals": approvals, "expected_version": version},
    )


def test_baseline_preview_comprehensive_and_scope(identities):
    e = identities
    p = project(e)
    c = e["client"]
    matrix = c.get(f"/v1/projects/{p}/policies", headers=auth(e["operator"]))
    assert matrix.status_code == 200
    rows = {(x["environment"], x["risk"]): x for x in matrix.json()}
    assert len(rows) == 9
    assert rows[("production", "high")]["required_approvals"] == 2
    assert rows[("staging", "high")]["required_approvals"] == 1
    assert rows[("dev", "low")]["required_approvals"] == 0
    assert all(x["source"] == "baseline" and x["version"] == 0 for x in rows.values())
    assert c.get(policy_url(p), headers=auth(e["outsider"])).status_code == 404
    assert c.get(f"/v1/projects/{p}/policies", headers=auth(e["outsider"])).status_code == 404
    assert c.get(policy_url(p, "unknown", "high"), headers=auth(e["operator"])).status_code == 422
    assert c.get(policy_url(p, "dev", "unknown"), headers=auth(e["operator"])).status_code == 422
    assert c.get(policy_url("f" * 32), headers=auth(e["admin"])).status_code == 404


def test_configured_policy_requires_admin_and_version_controls(identities):
    e = identities
    p = project(e)
    unauthorized = set_policy(e, p, 2, token=e["operator"])
    assert unauthorized.status_code == 403
    assert set_policy(e, p, 2, token=e["outsider"]).status_code == 404
    created = set_policy(e, p, 2)
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert created.json()["source"] == "project"
    assert created.json()["required_approvals"] == 2
    assert set_policy(e, p, 4, version=0).status_code == 409
    updated = set_policy(e, p, 3, version=1)
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["required_approvals"] == 3
    assert set_policy(e, p, 2, version=1).status_code == 409
    events = e["client"].get("/v1/audit/events", headers=auth(e["auditor"])).json()
    relevant = [x for x in events if x["action"] == "policy.updated"]
    assert len(relevant) == 2
    assert relevant[-1]["payload"]["version"] == 2
    assert e["client"].get("/v1/audit/verify", headers=auth(e["auditor"])).json()["valid"]


def test_policy_cannot_weaken_platform_safety_floor(identities):
    e = identities
    p = project(e)
    assert set_policy(e, p, 1, environment="production", risk="high").status_code == 422
    assert set_policy(e, p, 0, environment="production", risk="medium").status_code == 422
    assert set_policy(e, p, 0, environment="staging", risk="high").status_code == 422
    assert set_policy(e, p, 6).status_code == 422
    assert set_policy(e, p, -1).status_code == 422
    assert e["client"].get(policy_url(p), headers=auth(e["admin"])).json()["version"] == 0


def test_release_snapshots_preserved_after_policy_change(identities):
    e = identities
    p = project(e)
    before = release(e, p, idem="policy-snapshot-before", environment="staging", risk="low")
    assert before["required_approvals"] == 0
    assert before["policy_source"] == "baseline"
    assert before["policy_version"] is None
    assert set_policy(e, p, 2).status_code == 200
    after = release(e, p, idem="policy-snapshot-after", environment="staging", risk="low")
    assert after["required_approvals"] == 2
    assert after["policy_source"] == "project" and after["policy_version"] == 1
    assert set_policy(e, p, 3, version=1).status_code == 200
    newer = release(e, p, idem="policy-snapshot-newer", environment="staging", risk="low")
    assert newer["required_approvals"] == 3 and newer["policy_version"] == 2
    still_old = e["client"].get(f"/v1/releases/{after['id']}", headers=auth(e["operator"]))
    assert still_old.json()["required_approvals"] == 2
    assert still_old.json()["policy_version"] == 1
    replay = e["client"].post(
        "/v1/releases",
        headers={**auth(e["operator"]), "Idempotency-Key": "policy-snapshot-after"},
        json={"project_id": p, "environment": "staging", "risk": "low",
              "artifact_sha256": "a" * 64,
              "description": "Deploy build with security and reliability improvements"},
    )
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == after["id"]
    assert replay.json()["required_approvals"] == 2
    draft_submit = e["client"].post(
        f"/v1/releases/{before['id']}/submit", headers=auth(e["operator"]),
        json={"expected_version": 1},
    )
    assert draft_submit.json()["status"] == "approved"
    submitted = e["client"].post(
        f"/v1/releases/{after['id']}/submit", headers=auth(e["operator"]),
        json={"expected_version": 1},
    )
    assert submitted.json()["status"] == "submitted"
    assert e["client"].get("/v1/audit/verify", headers=auth(e["auditor"])).json()["valid"]


def test_three_approver_quorum_enforced(identities):
    e = identities
    p = project(e)
    assert set_policy(e, p, 3).status_code == 200
    item = release(e, p, idem="three-party-release", environment="staging", risk="low")
    c = e["client"]
    url = f"/v1/releases/{item['id']}"
    submit = c.post(url + "/submit", headers=auth(e["operator"]), json={"expected_version": 1})
    assert submit.json()["status"] == "submitted"
    for version, token in [(2, e["reviewer_a"]), (3, e["reviewer_b"])]:
        result = c.post(url + "/reviews", headers=auth(token),
                        json={"expected_version": version, "decision": "approve"})
        assert result.status_code == 200 and result.json()["status"] == "submitted"
    extra = c.post("/v1/keys", headers=auth(e["admin"]),
                   json={"label": "third reviewer", "role": "approver"})
    assert extra.status_code == 201
    result = c.post(url + "/reviews", headers=auth(extra.json()["key"]),
                    json={"expected_version": 4, "decision": "approve"})
    assert result.status_code == 200 and result.json()["status"] == "approved"
    assert result.json()["approval_count"] == 3


def test_independent_projects_and_tenants_cannot_inherit_policies(identities):
    e = identities
    p1 = project(e, "one-project")
    p2 = project(e, "two-project")
    assert set_policy(e, p1, 5).status_code == 200
    assert e["client"].get(policy_url(p2), headers=auth(e["admin"])).json()["required_approvals"] == 0
    assert set_policy(e, p1, 5, token=e["outsider"]).status_code == 404
    assert e["client"].put(policy_url(p1), headers=auth(e["admin"]),
                           json={"min_approvals": 2, "expected_version": 0, "extra": "not allowed"}).status_code == 422
