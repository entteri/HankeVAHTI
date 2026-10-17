
"""Create persistent application drafts.

Revision ID: 0008_application_drafts
Revises: 0007_multiple_search_criteria
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_application_drafts"
down_revision = "0007_multiple_search_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "funding_call_id",
            sa.Integer(),
            sa.ForeignKey("funding_calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_application_drafts_funding_call_id",
        "application_drafts",
        ["funding_call_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_drafts_funding_call_id",
        table_name="application_drafts",
    )
    op.drop_table("application_drafts")
