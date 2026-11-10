"""Operator-only CLI for tenant provisioning and audit verification.

Run from an isolated trusted terminal. Bootstrap secret is printed once. Never paste
credentials into CI logs, chat, screenshots, shell history, or version control.
"""

import argparse
import sys

from sqlalchemy import select

from shipgate.audit import append_audit, verify_audit
from shipgate.db import make_factory
from shipgate.models import ApiKey, AuditHead, Tenant
from shipgate.schemas import ProjectCreate
from shipgate.security import new_api_key


def bootstrap(slug: str, label: str) -> int:
    ProjectCreate(slug=slug)  # reuse consistent slug grammar
    factory = make_factory()
    with factory.begin() as session:
        if session.scalar(select(Tenant).where(Tenant.slug == slug)):
            print("tenant already exists; refusing to print or rotate keys", file=sys.stderr)
            return 2
        tenant = Tenant(slug=slug)
        session.add(tenant)
        session.flush()
        session.add(AuditHead(tenant_id=tenant.id, sequence=0, last_hash="0" * 64))
        raw_key, prefix, key_hash = new_api_key()
        actor = ApiKey(
            tenant_id=tenant.id, prefix=prefix, secret_hash=key_hash,
            role="admin", label=label,
        )
        session.add(actor)
        session.flush()
        append_audit(
            session, tenant_id=tenant.id, actor_key_id=actor.id,
            action="tenant.provisioned", subject_id=tenant.id,
            payload={"slug": slug, "admin_key_id": actor.id},
        )
    print(f"Tenant: {slug}\nAdmin key (shown ONCE): {raw_key}")
    print("Store in a secrets manager. Only a hash was saved in the database.")
    return 0


def audit_check(slug: str) -> int:
    factory = make_factory()
    with factory() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            print("tenant not found", file=sys.stderr)
            return 2
        valid, count, last_hash = verify_audit(session, tenant.id)
        print(f"valid={str(valid).lower()} events={count} last_hash={last_hash}")
        return 0 if valid else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="shipgate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    provision = subparsers.add_parser("bootstrap", help="Create tenant and one admin key")
    provision.add_argument("--tenant", required=True)
    provision.add_argument("--label", default="bootstrap-admin")
    verify = subparsers.add_parser("verify-audit", help="Verify a tenant hash chain")
    verify.add_argument("--tenant", required=True)
    args = parser.parse_args()
    if args.command == "bootstrap":
        sys.exit(bootstrap(args.tenant, args.label))
    sys.exit(audit_check(args.tenant))


if __name__ == "__main__":
    main()
