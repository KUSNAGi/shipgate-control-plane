import hashlib
import hmac
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shipgate.models import ApiKey

VALID_ROLES = frozenset({"admin", "operator", "approver", "auditor"})


def new_api_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(7)
    secret = secrets.token_urlsafe(36)
    return f"sg_{prefix}_{secret}", prefix, hashlib.sha256(secret.encode()).hexdigest()


def authenticate(session: Session, value: str | None) -> ApiKey:
    if not value or len(value) > 160:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    parts = value.split("_", 2)
    if len(parts) != 3 or parts[0] != "sg" or not parts[1] or not parts[2]:
        raise HTTPException(status_code=401, detail="invalid API key")
    key = session.scalar(select(ApiKey).where(ApiKey.prefix == parts[1], ApiKey.revoked.is_(False)))
    candidate_hash = hashlib.sha256(parts[2].encode()).hexdigest()
    if not key or not hmac.compare_digest(candidate_hash, key.secret_hash):
        raise HTTPException(status_code=401, detail="invalid API key")
    return key


def require_role(actor: ApiKey, *roles: str) -> None:
    if actor.role not in roles:
        raise HTTPException(status_code=403, detail="insufficient role")
