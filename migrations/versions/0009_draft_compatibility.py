"""Reconcile databases from the local EURA prototype with the master schema.

Revision ID: 0009_draft_compatibility
Revises: 0008_application_draft

The prototype used the unpublished 0008_application_draft revision ID for a
JSON application_drafts table. Its revised upgrade now follows master's text
draft migration and creates eura_application_drafts. Already-stamped prototype
databases skip that upgrade, so this bridge renames their existing JSON table
and creates the missing text table. Fresh and master databases need no repair.
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_draft_compatibility"
down_revision = "0008_application_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("application_drafts")}
    if "content_json" not in columns:
        return
    if inspector.has_table("eura_application_drafts"):
        raise RuntimeError("Both legacy and new EURA tables exist; refusing to overwrite drafts.")
    op.rename_table("application_drafts", "eura_application_drafts")
    op.create_table(
        "application_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("funding_call_id", sa.Integer(), sa.ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_application_drafts_funding_call_id", "application_drafts", ["funding_call_id"])


def downgrade() -> None:
    # The preceding revision now describes both separate tables. Keep their
    # data intact; its downgrade removes only the EURA table if requested.
    pass
