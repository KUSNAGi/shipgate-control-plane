"""API-key expiration and rotation support.

Revision ID: 17d684e41a63
Revises: 99cb612a7ca9
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa

revision = "17d684e41a63"
down_revision = "99cb612a7ca9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL preserves legacy key behavior so existing operators can rotate safely.
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
