"""Add Haeavustuksia search criteria.

Revision ID: 0004_haeavustuksia_search_criteria
Revises: 0003_haeavustuksia_direct_links
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_haeavustuksia_search_criteria"
down_revision = "0003_haeavustuksia_direct_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "haeavustuksia_search_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grant_type", sa.String(length=100)),
        sa.Column("show_future", sa.Boolean(), nullable=False),
        sa.Column("show_ongoing", sa.Boolean(), nullable=False),
        sa.Column("authority", sa.String(length=100)),
    )


def downgrade() -> None:
    op.drop_table("haeavustuksia_search_criteria")
