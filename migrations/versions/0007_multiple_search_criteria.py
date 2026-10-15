"""Allow multiple values in dropdown search criteria.

Revision ID: 0007_multiple_search_criteria
Revises: 0006_evaluation_decisions_matches
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "0007_multiple_search_criteria"
down_revision = "0006_evaluation_decisions_matches"
branch_labels = None
depends_on = None


def _migrate_values(table: str, fields: dict[str, str]) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id, {', '.join(fields)} FROM {table}")).mappings()
    for row in rows:
        values = {new: json.dumps([row[old]] if row[old] else []) for old, new in fields.items()}
        values["id"] = row["id"]
        assignments = ", ".join(f"{new} = :{new}" for new in fields.values())
        connection.execute(sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"), values)


def upgrade() -> None:
    for name in ("funds", "areas", "authorities"):
        op.add_column("eura_search_criteria", sa.Column(name, sa.JSON(), nullable=True))
    for name in ("grant_types", "authorities"):
        op.add_column("haeavustuksia_search_criteria", sa.Column(name, sa.JSON(), nullable=True))

    _migrate_values("eura_search_criteria", {"fund": "funds", "area": "areas", "authority": "authorities"})
    _migrate_values("haeavustuksia_search_criteria", {"grant_type": "grant_types", "authority": "authorities"})

    with op.batch_alter_table("eura_search_criteria") as batch:
        for name in ("funds", "areas", "authorities"):
            batch.alter_column(name, nullable=False)
        for name in ("fund", "area", "authority"):
            batch.drop_column(name)
    with op.batch_alter_table("haeavustuksia_search_criteria") as batch:
        for name in ("grant_types", "authorities"):
            batch.alter_column(name, nullable=False)
        for name in ("grant_type", "authority"):
            batch.drop_column(name)


def downgrade() -> None:
    for name in ("fund", "area", "authority"):
        op.add_column("eura_search_criteria", sa.Column(name, sa.String(length=100)))
    for name in ("grant_type", "authority"):
        op.add_column("haeavustuksia_search_criteria", sa.Column(name, sa.String(length=100)))

    connection = op.get_bind()
    for table, fields in (
        ("eura_search_criteria", {"funds": "fund", "areas": "area", "authorities": "authority"}),
        ("haeavustuksia_search_criteria", {"grant_types": "grant_type", "authorities": "authority"}),
    ):
        rows = connection.execute(sa.text(f"SELECT id, {', '.join(fields)} FROM {table}")).mappings()
        for row in rows:
            values = {old: (json.loads(row[new])[0] if json.loads(row[new]) else None) for new, old in fields.items()}
            values["id"] = row["id"]
            assignments = ", ".join(f"{old} = :{old}" for old in fields.values())
            connection.execute(sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"), values)

    with op.batch_alter_table("eura_search_criteria") as batch:
        for name in ("funds", "areas", "authorities"):
            batch.drop_column(name)
    with op.batch_alter_table("haeavustuksia_search_criteria") as batch:
        for name in ("grant_types", "authorities"):
            batch.drop_column(name)
