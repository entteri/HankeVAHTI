"""Store one EURA/Word draft per funding call, separately from text drafts.

The revision ID is retained for local prototypes already stamped at this
revision. Revision 0009 reconciles their earlier table layout without data loss.

Revision ID: 0008_application_draft
Revises: 0008_application_drafts
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_application_draft"
down_revision = "0008_application_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eura_application_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("funding_call_id", sa.Integer(), sa.ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("funding_call_id", name="uq_application_drafts_funding_call_id"),
    )


def downgrade() -> None:
    op.drop_table("eura_application_drafts")
