"""Backfill direct Haeavustuksia call links.

Revision ID: 0003_haeavustuksia_direct_links
Revises: 0002_eura_search_criteria
"""

from alembic import op

revision = "0003_haeavustuksia_direct_links"
down_revision = "0002_eura_search_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE funding_calls SET source_url = "
        "'https://www.haeavustuksia.fi/fi/haku/' || source_id "
        "WHERE source = 'HAEAVUSTUKSIA'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE funding_calls SET source_url = "
        "'https://www.haeavustuksia.fi/api/haku/list-items' "
        "WHERE source = 'HAEAVUSTUKSIA'"
    )
