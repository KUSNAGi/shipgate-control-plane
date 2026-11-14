"""Tenant-scoped approval policies; enforce non-negotiable global safety floors."""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shipgate.audit import append_audit
from shipgate.models import ApiKey, Project, ProjectPolicy, now_utc
from shipgate.security import require_role

ENVIRONMENTS = ("dev", "staging", "production")
RISKS = ("low", "medium", "high")


def required_approvals(environment: str, risk: str) -> int:
    if environment == "production":
        return 2 if risk == "high" else 1
    return 1 if environment == "staging" and risk == "high" else 0


@dataclass(frozen=True)
class Resolution:
    project_id: str
    environment: str
    risk: str
    baseline_approvals: int
    required_approvals: int
    source: str
    version: int


def find_project(db: Session, actor: ApiKey, project_id: str, *, lock: bool = False) -> Project:
    stmt = select(Project).where(
        Project.tenant_id == actor.tenant_id, Project.id == project_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    project = db.scalar(stmt)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def resolve_policy(db: Session, actor: ApiKey, project_id: str,
                   environment: str, risk: str) -> Resolution:
    baseline = required_approvals(environment, risk)
    record = db.scalar(select(ProjectPolicy).where(
        ProjectPolicy.tenant_id == actor.tenant_id,
        ProjectPolicy.project_id == project_id,
        ProjectPolicy.environment == environment, ProjectPolicy.risk == risk,
    ))
    return Resolution(
        project_id, environment, risk, baseline,
        max(baseline, record.min_approvals) if record else baseline,
        "project" if record else "baseline", record.version if record else 0,
    )


def update_policy(db: Session, actor: ApiKey, project_id: str,
                  environment: str, risk: str, min_approvals: int,
                  expected_version: int) -> Resolution:
    require_role(actor, "admin")
    # The parent lock serializes competing inserts for an absent policy on PostgreSQL.
    find_project(db, actor, project_id, lock=True)
    baseline = required_approvals(environment, risk)
    if min_approvals < baseline:
        raise HTTPException(422, f"minimum below platform safety floor ({baseline})")
    record = db.scalar(select(ProjectPolicy).where(
        ProjectPolicy.tenant_id == actor.tenant_id,
        ProjectPolicy.project_id == project_id,
        ProjectPolicy.environment == environment, ProjectPolicy.risk == risk,
    ).with_for_update())
    current_version = record.version if record else 0
    if expected_version != current_version:
        raise HTTPException(409, f"policy version conflict: current version is {current_version}")
    if record is None:
        record = ProjectPolicy(
            tenant_id=actor.tenant_id, project_id=project_id,
            environment=environment, risk=risk, min_approvals=min_approvals,
            version=1,
        )
        db.add(record)
    else:
        record.min_approvals = min_approvals
        record.version += 1
        record.updated_at = now_utc()
    db.flush()
    append_audit(
        db, tenant_id=actor.tenant_id, actor_key_id=actor.id,
        action="policy.updated", subject_id=project_id,
        payload={"environment": environment, "risk": risk,
                 "min_approvals": min_approvals, "version": record.version},
    )
    return resolve_policy(db, actor, project_id, environment, risk)
