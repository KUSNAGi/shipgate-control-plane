"""Transactional policy and release state transitions.

All mutations run in the request's single database transaction. PostgreSQL row
locks serialize release decisions and audit chain mutation across workers.
"""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from shipgate.audit import append_audit
from shipgate.policy import resolve_policy
from shipgate.models import (
    ApiKey, Approval, IdempotencyRecord, Project, Release, now_utc,
)
from shipgate.schemas import ReleaseCreate, ReleaseOut
from shipgate.security import require_role


def fail(code: int, detail: str) -> None:
    raise HTTPException(status_code=code, detail=detail)


def select_release(session: Session, actor: ApiKey, release_id: str, *, lock: bool = False) -> Release:
    statement = select(Release).where(Release.id == release_id, Release.tenant_id == actor.tenant_id)
    if lock:
        statement = statement.with_for_update()
    release = session.scalar(statement)
    if release is None:
        fail(404, "release not found")
    return release


def present_release(session: Session, release: Release) -> ReleaseOut:
    count = session.scalar(
        select(func.count()).select_from(Approval).where(
            Approval.release_id == release.id, Approval.decision == "approve"
        )
    )
    return ReleaseOut(
        id=release.id, project_id=release.project_id, environment=release.environment,
        artifact_sha256=release.artifact_sha256, risk=release.risk,
        description=release.description, status=release.status, version=release.version,
        required_approvals=release.required_approvals,
        policy_source=release.policy_source, policy_version=release.policy_version,
        approval_count=count or 0,
        created_by=release.created_by, completion_evidence=release.completion_evidence,
        created_at=release.created_at, updated_at=release.updated_at,
    )


def hash_create_body(body: ReleaseCreate) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_release(session: Session, actor: ApiKey, body: ReleaseCreate,
                   idempotency_key: str) -> tuple[Release, bool]:
    require_role(actor, "admin", "operator")
    if not 8 <= len(idempotency_key) <= 128 or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key):
        fail(422, "Idempotency-Key must contain 8-128 visible ASCII characters")
    body_hash = hash_create_body(body)
    if session.bind.dialect.name == "postgresql":
        # Serialize concurrent retries of the same key before the uniqueness check.
        # Database row-level uniqueness remains a defense-in-depth constraint.
        advisory_id = int.from_bytes(
            hashlib.sha256(
                f"{actor.tenant_id}:{actor.id}:{idempotency_key}".encode()
            ).digest()[:8], "big", signed=True,
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": advisory_id})
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == actor.tenant_id,
            IdempotencyRecord.actor_key_id == actor.id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if record is not None:
        if record.body_hash != body_hash:
            fail(409, "idempotency key reused with a different request")
        return select_release(session, actor, record.release_id), True

    # Serialize creation against project-policy writes on PostgreSQL.
    project = session.scalar(select(Project).where(
        Project.id == body.project_id, Project.tenant_id == actor.tenant_id,
    ).with_for_update())
    if project is None:
        fail(404, "project not found")
    policy = resolve_policy(session, actor, project.id, body.environment, body.risk)
    release = Release(
        tenant_id=actor.tenant_id, project_id=project.id, created_by=actor.id,
        environment=body.environment, artifact_sha256=body.artifact_sha256,
        risk=body.risk, description=body.description,
        required_approvals=policy.required_approvals,
        policy_source=policy.source, policy_version=policy.version or None,
        status="draft", version=1,
    )
    session.add(release)
    session.flush()
    session.add(IdempotencyRecord(
        tenant_id=actor.tenant_id, actor_key_id=actor.id,
        idempotency_key=idempotency_key, body_hash=body_hash, release_id=release.id,
    ))
    append_audit(
        session, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="release.created", subject_id=release.id,
        payload={"project_id": project.id, "environment": body.environment,
                 "artifact_sha256": body.artifact_sha256, "risk": body.risk,
                 "required_approvals": policy.required_approvals,
                 "policy_source": policy.source, "policy_version": policy.version},
    )
    session.flush()
    return release, False


def change_state(release: Release, new_status: str) -> None:
    release.status = new_status
    release.version += 1
    release.updated_at = now_utc()


def ensure_version(release: Release, expected_version: int) -> None:
    if release.version != expected_version:
        fail(409, f"version conflict: current version is {release.version}")


def submit_release(session: Session, actor: ApiKey, release_id: str, version: int) -> Release:
    require_role(actor, "admin", "operator")
    release = select_release(session, actor, release_id, lock=True)
    ensure_version(release, version)
    if release.status != "draft":
        fail(409, "only draft releases can be submitted")
    if actor.id != release.created_by and actor.role != "admin":
        fail(403, "only the author or an admin may submit")
    change_state(release, "approved" if release.required_approvals == 0 else "submitted")
    append_audit(
        session, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="release.submitted", subject_id=release.id,
        payload={"status": release.status, "required_approvals": release.required_approvals},
    )
    session.flush()
    return release


def review_release(session: Session, actor: ApiKey, release_id: str, version: int,
                   decision: str, note: str) -> Release:
    require_role(actor, "admin", "approver")
    release = select_release(session, actor, release_id, lock=True)
    ensure_version(release, version)
    if release.status != "submitted":
        fail(409, "only submitted releases can be reviewed")
    if actor.id == release.created_by:
        fail(403, "author cannot approve or reject their own release")
    prior = session.scalar(select(Approval).where(
        Approval.release_id == release.id, Approval.reviewer_key_id == actor.id,
    ))
    if prior is not None:
        fail(409, "reviewer has already decided on this release")
    session.add(Approval(
        tenant_id=actor.tenant_id, release_id=release.id,
        reviewer_key_id=actor.id, decision=decision, note=note,
    ))
    session.flush()
    if decision == "reject":
        change_state(release, "rejected")
    else:
        count = session.scalar(select(func.count()).select_from(Approval).where(
            Approval.release_id == release.id, Approval.decision == "approve"
        )) or 0
        change_state(release, "approved" if count >= release.required_approvals else "submitted")
    append_audit(
        session, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="release.review_approved" if decision == "approve" else "release.rejected",
        subject_id=release.id, payload={"status": release.status, "note": note},
    )
    session.flush()
    return release


def complete_release(session: Session, actor: ApiKey, release_id: str, version: int,
                     observed_sha: str, evidence_url: str) -> Release:
    require_role(actor, "admin", "operator")
    release = select_release(session, actor, release_id, lock=True)
    ensure_version(release, version)
    if release.status != "approved":
        fail(409, "only approved releases can record deployment evidence")
    if observed_sha != release.artifact_sha256:
        fail(409, "observed artifact digest differs from approved digest")
    change_state(release, "completed")
    release.completion_evidence = evidence_url
    append_audit(
        session, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="release.completed", subject_id=release.id,
        payload={"artifact_sha256": observed_sha, "evidence_url": evidence_url},
    )
    session.flush()
    return release


def cancel_release(session: Session, actor: ApiKey, release_id: str, version: int) -> Release:
    require_role(actor, "admin", "operator")
    release = select_release(session, actor, release_id, lock=True)
    ensure_version(release, version)
    if release.status not in {"draft", "submitted", "approved"}:
        fail(409, "release is already terminal")
    if actor.id != release.created_by and actor.role != "admin":
        fail(403, "only the author or an admin may cancel")
    change_state(release, "cancelled")
    append_audit(
        session, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="release.cancelled", subject_id=release.id, payload={},
    )
    session.flush()
    return release
