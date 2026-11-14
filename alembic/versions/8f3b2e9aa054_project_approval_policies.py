"""Project approval policies with per-release provenance snapshots.

Revision ID: 8f3b2e9aa054
Revises: 17d684e41a63
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa

revision = "8f3b2e9aa054"
down_revision = "17d684e41a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_policies",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("risk", sa.String(10), nullable=False),
        sa.Column("min_approvals", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="fk_project_policy_project_tenant", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "project_id", "environment", "risk",
                            name="uq_project_policy_scope"),
    )
    op.add_column("releases", sa.Column(
        "policy_source", sa.String(20), nullable=False, server_default="baseline",
    ))
    op.add_column("releases", sa.Column("policy_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("releases", "policy_version")
    op.drop_column("releases", "policy_source")
    op.drop_table("project_policies")
