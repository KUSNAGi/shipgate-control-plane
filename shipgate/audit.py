"""Application-level SHA-256 hash chain, scoped and serialized per tenant.

This detects accidental or unauthorized event rewriting given a separately trusted chain head.
It does not protect against a database superuser rewriting both events and the chain head.
For external tamper evidence, anchor the last hash in independent storage.
"""

import hashlib
import json
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from shipgate.models import AuditEvent, AuditHead, now_utc

GENESIS = "0" * 64


def canonical_event(*, tenant_id: str, sequence: int, actor_key_id: str | None,
                    action: str, subject_id: str, payload: dict, created_at: str) -> str:
    return json.dumps(
        {
            "tenant_id": tenant_id, "sequence": sequence, "actor_key_id": actor_key_id,
            "action": action, "subject_id": subject_id, "payload": payload,
            "created_at": created_at,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def event_hash(previous_hash: str, content: str) -> str:
    return hashlib.sha256((previous_hash + "\n" + content).encode()).hexdigest()


def append_audit(session: Session, *, tenant_id: str, actor_key_id: str | None,
                 action: str, subject_id: str, payload: dict) -> AuditEvent:
    head = session.scalar(
        select(AuditHead).where(AuditHead.tenant_id == tenant_id).with_for_update()
    )
    if head is None:
        raise RuntimeError("tenant audit head missing: provisioning incomplete")
    created_at = now_utc()
    sequence = head.sequence + 1
    content = canonical_event(
        tenant_id=tenant_id, sequence=sequence, actor_key_id=actor_key_id,
        action=action, subject_id=subject_id, payload=payload,
        created_at=created_at.isoformat(),
    )
    digest = event_hash(head.last_hash, content)
    event = AuditEvent(
        tenant_id=tenant_id, sequence=sequence, actor_key_id=actor_key_id,
        action=action, subject_id=subject_id, payload=payload,
        previous_hash=head.last_hash, hash=digest, created_at=created_at,
    )
    session.add(event)
    head.sequence = sequence
    head.last_hash = digest
    return event


def verify_audit(session: Session, tenant_id: str) -> tuple[bool, int, str]:
    head = session.get(AuditHead, tenant_id)
    if head is None:
        return False, 0, GENESIS
    previous = GENESIS
    expected_seq = 0
    for event in session.scalars(
        select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.sequence)
    ):
        expected_seq += 1
        actual_created = event.created_at
        # SQLite drops tzinfo on read; normalize to UTC before canonical serialization.
        if actual_created.tzinfo is None:
            actual_created = actual_created.replace(tzinfo=timezone.utc)
        else:
            actual_created = actual_created.astimezone(timezone.utc)
        content = canonical_event(
            tenant_id=tenant_id, sequence=event.sequence, actor_key_id=event.actor_key_id,
            action=event.action, subject_id=event.subject_id, payload=event.payload,
            created_at=actual_created.isoformat(),
        )
        calculated = event_hash(previous, content)
        if event.sequence != expected_seq or event.previous_hash != previous or calculated != event.hash:
            return False, expected_seq, previous
        previous = event.hash
    return head.sequence == expected_seq and head.last_hash == previous, expected_seq, previous
