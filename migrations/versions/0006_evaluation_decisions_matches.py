"""Store rejection timestamps and structured relevance matches.

Revision ID: 0006_evaluation_decisions_matches
Revises: 0005_ai_summary
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_evaluation_decisions_matches"
down_revision = "0005_ai_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluations", sa.Column("matched_keywords", sa.JSON(none_as_null=True), nullable=True))
    op.add_column("evaluations", sa.Column("matched_excluded_keywords", sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evaluations") as batch:
        batch.drop_column("matched_excluded_keywords")
        batch.drop_column("matched_keywords")
        batch.drop_column("rejected_at")
