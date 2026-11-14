from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG = r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$"
SHA256 = r"^[a-f0-9]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictModel):
    slug: str = Field(pattern=SLUG)
    description: str = Field(default="", max_length=500)


class ProjectOut(StrictModel):
    id: str
    slug: str
    description: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class KeyCreate(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    role: Literal["admin", "operator", "approver", "auditor"]
    ttl_hours: int = Field(default=720, ge=1, le=2160)


class KeyRotate(StrictModel):
    ttl_hours: int = Field(default=720, ge=1, le=2160)


class KeyCreated(StrictModel):
    id: str
    label: str
    role: str
    key: str
    expires_at: datetime


class KeyOut(StrictModel):
    id: str
    label: str
    role: str
    prefix: str
    revoked: bool
    expires_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReleaseCreate(StrictModel):
    project_id: str = Field(min_length=32, max_length=32)
    environment: Literal["dev", "staging", "production"]
    artifact_sha256: str = Field(pattern=SHA256)
    risk: Literal["low", "medium", "high"]
    description: str = Field(min_length=12, max_length=2000)


class VersionedAction(StrictModel):
    expected_version: int = Field(ge=1)


class ReviewAction(VersionedAction):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class CompleteAction(VersionedAction):
    observed_artifact_sha256: str = Field(pattern=SHA256)
    evidence_url: str = Field(min_length=15, max_length=500)

    @field_validator("evidence_url")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        # URLs enter the durable audit log: reject ambiguous or credential-bearing input.
        if any(c.isspace() or ord(c) < 33 or c == "\\" for c in value):
            raise ValueError("evidence_url must be an HTTPS URL without whitespace or backslashes")
        try:
            parsed = urlsplit(value)
            valid = (
                value.startswith("https://")
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.port != 0
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("evidence_url requires a valid HTTPS host and no URL credentials")
        return value


class ReleaseOut(StrictModel):
    id: str
    project_id: str
    environment: str
    artifact_sha256: str
    risk: str
    description: str
    status: str
    version: int
    required_approvals: int
    policy_source: str
    policy_version: int | None
    approval_count: int
    created_by: str
    completion_evidence: str | None
    created_at: datetime
    updated_at: datetime


class AuditOut(StrictModel):
    sequence: int
    action: str
    subject_id: str
    actor_key_id: str | None
    payload: dict
    previous_hash: str
    hash: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AuditVerification(StrictModel):
    valid: bool
    event_count: int
    last_hash: str


class Page(StrictModel):
    # Intentionally offset-based for small read-bound administrative datasets.
    items: list
    limit: int
    offset: int


class PolicyUpdate(StrictModel):
    min_approvals: int = Field(ge=0, le=5)
    expected_version: int = Field(ge=0)


class PolicyOut(StrictModel):
    project_id: str
    environment: Literal["dev", "staging", "production"]
    risk: Literal["low", "medium", "high"]
    baseline_approvals: int
    required_approvals: int
    source: Literal["baseline", "project"]
    version: int
