"""Add EURA search criteria and direct announcement links.

Revision ID: 0002_eura_search_criteria
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_eura_search_criteria"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eura_search_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund", sa.String(length=100)),
        sa.Column("area", sa.String(length=100)),
        sa.Column("authority", sa.String(length=100)),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("call_identifier", sa.String(length=255)),
    )
    op.execute(
        "UPDATE funding_calls SET source_url = "
        "'https://eura2021.fi/hakuilmoitukset/hakuilmoitus/' || source_id || '/' "
        "WHERE source = 'EURA'"
    )


def downgrade() -> None:
    op.drop_table("eura_search_criteria")
