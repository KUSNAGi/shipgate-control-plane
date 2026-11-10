"""A deployment evidence link must not introduce malformed or credential-bearing URLs."""

import pytest
from pydantic import ValidationError

from shipgate.schemas import CompleteAction
from tests.conftest import auth, project, release


@pytest.mark.parametrize("url", [
    "http://ci.example.org/runs/42",  # not TLS
    "https:///missing-host/runs/42",  # empty authority
    "https://user:password@ci.example.org/runs/42",  # credential leak
    "https://ci.example.org\\@unexpected.example/runs/42",  # ambiguous backslash
    "https://ci.example.org:99999/runs/42",  # invalid port
    "https://ci.example.org/\nunsafe",  # control characters
])
def test_invalid_evidence_url_is_rejected(url):
    with pytest.raises(ValidationError):
        CompleteAction(expected_version=1, observed_artifact_sha256="a" * 64,
                       evidence_url=url)


def test_valid_https_evidence_url_is_preserved():
    url = "https://ci.example.org/runs/42?artifact=abc"
    action = CompleteAction(expected_version=1, observed_artifact_sha256="a" * 64,
                            evidence_url=url)
    assert action.evidence_url == url


def test_api_rejects_malformed_evidence_without_completing_release(identities):
    env = identities
    client = env["client"]
    item = release(env, project(env), environment="staging", risk="low")
    submitted = client.post(
        f"/v1/releases/{item['id']}/submit", headers=auth(env["operator"]),
        json={"expected_version": 1},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "approved"

    invalid = client.post(
        f"/v1/releases/{item['id']}/complete", headers=auth(env["operator"]),
        json={"expected_version": 2, "observed_artifact_sha256": "a" * 64,
              "evidence_url": "https://user:password@ci.example.org/runs/42"},
    )
    assert invalid.status_code == 422
    readback = client.get(f"/v1/releases/{item['id']}", headers=auth(env["operator"]))
    assert readback.json()["status"] == "approved"
    assert readback.json()["completion_evidence"] is None
