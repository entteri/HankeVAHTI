"""Add a separate AI summary for selected funding calls.

Revision ID: 0005_ai_summary
Revises: 0004_haeavustuksia_search_criteria
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_ai_summary"
down_revision = "0004_haeavustuksia_search_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("ai_summary", sa.Text()))


def downgrade() -> None:
    op.drop_column("evaluations", "ai_summary")
