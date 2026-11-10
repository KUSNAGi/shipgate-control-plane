"""HTTP service; all state transitions are transactional and tenant-scoped."""

import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware

from shipgate.audit import append_audit, verify_audit
from shipgate.config import Settings, get_settings
from shipgate.db import make_factory
from shipgate.models import ApiKey, AuditEvent, Project, Release
from shipgate.schemas import (
    AuditOut, AuditVerification, CompleteAction, KeyCreate, KeyCreated, KeyOut,
    ProjectCreate, ProjectOut, ReleaseCreate, ReleaseOut, ReviewAction,
    VersionedAction,
)
from shipgate.security import authenticate, new_api_key, require_role
from shipgate.service import (
    cancel_release, complete_release, create_release, present_release,
    review_release, select_release, submit_release,
)

logger = logging.getLogger("shipgate")


def create_app(factory: sessionmaker | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_serving()
    factory = factory or make_factory(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Schema migrations are explicit: alembic upgrade head before startup.
        logger.info("shipgate API starting; database migrations must already be applied")
        yield

    app = FastAPI(
        title="ShipGate Control Plane", version="0.1.0", lifespan=lifespan,
        description="An independent release approval and evidence recording service.",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @app.middleware("http")
    async def request_controls(request: Request, call_next):
        request_id = uuid4().hex

        def reject(status_code: int, detail: str) -> JSONResponse:
            response = JSONResponse(status_code=status_code, content={"detail": detail})
            response.headers["X-Request-ID"] = request_id
            response.headers["Cache-Control"] = "no-store"
            return response

        if request.method in {"POST", "PUT", "PATCH"}:
            # Reverse proxy must also enforce body size; stream is bounded here.
            try:
                content_length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return reject(400, "bad Content-Length")
            if content_length > settings.max_request_bytes:
                return reject(413, "request too large")
            chunks: list[bytes] = []
            total = 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > settings.max_request_bytes:
                    return reject(413, "request too large")
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def db_session():
        with factory.begin() as session:
            yield session

    Db = Annotated[Session, Depends(db_session)]

    def principal(
        db: Db, x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> ApiKey:
        return authenticate(db, x_api_key)

    Principal = Annotated[ApiKey, Depends(principal)]

    @app.get("/health/live", tags=["Health"])
    def live():
        return {"status": "live"}

    @app.get("/health/ready", tags=["Health"])
    def ready(db: Db):
        try:
            db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one()
        except Exception:
            raise HTTPException(status_code=503, detail="database unavailable") from None
        return {"status": "ready"}

    @app.get("/v1/me", tags=["Auth"])
    def me(actor: Principal):
        return {"tenant_id": actor.tenant_id, "key_id": actor.id, "role": actor.role}

    @app.post("/v1/keys", status_code=201, response_model=KeyCreated, tags=["Auth"])
    def issue_key(body: KeyCreate, actor: Principal, db: Db):
        require_role(actor, "admin")
        secret, prefix, digest = new_api_key()
        record = ApiKey(
            tenant_id=actor.tenant_id, prefix=prefix, secret_hash=digest,
            role=body.role, label=body.label,
        )
        db.add(record)
        db.flush()
        append_audit(
            db, tenant_id=actor.tenant_id, actor_key_id=actor.id,
            action="key.created", subject_id=record.id,
            payload={"label": body.label, "role": body.role},
        )
        return KeyCreated(id=record.id, label=body.label, role=body.role, key=secret)

    @app.get("/v1/keys", response_model=list[KeyOut], tags=["Auth"])
    def list_keys(actor: Principal, db: Db):
        require_role(actor, "admin", "auditor")
        return db.scalars(select(ApiKey).where(ApiKey.tenant_id == actor.tenant_id)
                          .order_by(ApiKey.created_at, ApiKey.id).limit(100)).all()

    @app.post("/v1/keys/{key_id}/revoke", response_model=KeyOut, tags=["Auth"])
    def revoke_key(key_id: str, actor: Principal, db: Db):
        require_role(actor, "admin")
        key = db.scalar(select(ApiKey).where(
            ApiKey.id == key_id, ApiKey.tenant_id == actor.tenant_id,
        ).with_for_update())
        if not key:
            raise HTTPException(status_code=404, detail="key not found")
        if key.id == actor.id:
            raise HTTPException(status_code=409, detail="cannot self-revoke")
        if key.revoked:
            raise HTTPException(status_code=409, detail="key already revoked")
        key.revoked = True
        append_audit(
            db, tenant_id=actor.tenant_id, actor_key_id=actor.id,
            action="key.revoked", subject_id=key.id, payload={},
        )
        db.flush()
        return key

    @app.post("/v1/projects", status_code=201, response_model=ProjectOut, tags=["Projects"])
    def make_project(body: ProjectCreate, actor: Principal, db: Db):
        require_role(actor, "admin")
        # Serializes competing project slug creations on PostgreSQL.
        from shipgate.models import Tenant
        db.scalar(select(Tenant).where(Tenant.id == actor.tenant_id).with_for_update())
        existing = db.scalar(select(Project).where(
            Project.tenant_id == actor.tenant_id, Project.slug == body.slug,
        ))
        if existing:
            raise HTTPException(status_code=409, detail="project slug already exists")
        project = Project(
            tenant_id=actor.tenant_id, slug=body.slug, description=body.description,
        )
        db.add(project)
        db.flush()
        append_audit(
            db, tenant_id=actor.tenant_id, actor_key_id=actor.id,
            action="project.created", subject_id=project.id,
            payload={"slug": project.slug},
        )
        return project

    @app.get("/v1/projects", response_model=list[ProjectOut], tags=["Projects"])
    def projects(actor: Principal, db: Db):
        return db.scalars(select(Project).where(
            Project.tenant_id == actor.tenant_id,
        ).order_by(Project.slug).limit(100)).all()

    @app.post("/v1/releases", status_code=201, response_model=ReleaseOut, tags=["Releases"])
    def make_release(body: ReleaseCreate, actor: Principal, db: Db,
                     idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
        if idempotency_key is None:
            raise HTTPException(status_code=422, detail="Idempotency-Key is required")
        release, _replayed = create_release(db, actor, body, idempotency_key)
        return present_release(db, release)

    @app.get("/v1/releases", response_model=list[ReleaseOut], tags=["Releases"])
    def releases(actor: Principal, db: Db,
                 limit: int = Query(default=50, ge=1, le=100),
                 offset: int = Query(default=0, ge=0),
                 status: str | None = Query(default=None, max_length=20)):
        stmt = select(Release).where(Release.tenant_id == actor.tenant_id)
        if status:
            if status not in {"draft", "submitted", "approved", "rejected", "cancelled", "completed"}:
                raise HTTPException(status_code=422, detail="invalid status filter")
            stmt = stmt.where(Release.status == status)
        results = db.scalars(stmt.order_by(Release.created_at.desc(), Release.id.desc())
                             .limit(limit).offset(offset)).all()
        return [present_release(db, release) for release in results]

    @app.get("/v1/releases/{release_id}", response_model=ReleaseOut, tags=["Releases"])
    def get_release(release_id: str, actor: Principal, db: Db):
        return present_release(db, select_release(db, actor, release_id))

    @app.post("/v1/releases/{release_id}/submit", response_model=ReleaseOut, tags=["Releases"])
    def submit(release_id: str, body: VersionedAction, actor: Principal, db: Db):
        return present_release(db, submit_release(db, actor, release_id, body.expected_version))

    @app.post("/v1/releases/{release_id}/reviews", response_model=ReleaseOut, tags=["Releases"])
    def review(release_id: str, body: ReviewAction, actor: Principal, db: Db):
        return present_release(db, review_release(
            db, actor, release_id, body.expected_version, body.decision, body.note,
        ))

    @app.post("/v1/releases/{release_id}/complete", response_model=ReleaseOut, tags=["Releases"])
    def complete(release_id: str, body: CompleteAction, actor: Principal, db: Db):
        return present_release(db, complete_release(
            db, actor, release_id, body.expected_version,
            body.observed_artifact_sha256, body.evidence_url,
        ))

    @app.post("/v1/releases/{release_id}/cancel", response_model=ReleaseOut, tags=["Releases"])
    def cancel(release_id: str, body: VersionedAction, actor: Principal, db: Db):
        return present_release(db, cancel_release(db, actor, release_id, body.expected_version))

    @app.get("/v1/audit/events", response_model=list[AuditOut], tags=["Audit"])
    def audit_events(actor: Principal, db: Db,
                     after: int = Query(default=0, ge=0),
                     limit: int = Query(default=100, ge=1, le=500)):
        require_role(actor, "admin", "auditor")
        return db.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == actor.tenant_id, AuditEvent.sequence > after,
            ).order_by(AuditEvent.sequence).limit(limit)
        ).all()

    @app.get("/v1/audit/verify", response_model=AuditVerification, tags=["Audit"])
    def audit_verify(actor: Principal, db: Db):
        require_role(actor, "admin", "auditor")
        valid, count, last_hash = verify_audit(db, actor.tenant_id)
        return AuditVerification(valid=valid, event_count=count, last_hash=last_hash)

    return app


app = create_app()
