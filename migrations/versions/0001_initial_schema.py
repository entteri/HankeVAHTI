"""Initial schema for funding calls, evaluations, participations and profiles.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funding_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("call_identifier", sa.String(length=255)),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("fund", sa.String(length=255)),
        sa.Column("category", sa.String(length=255)),
        sa.Column("source_url", sa.String(length=2048)),
        sa.Column("application_start_date", sa.Date()),
        sa.Column("application_end_date", sa.Date()),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_id", name="uq_funding_calls_source_source_id"),
    )
    op.create_table(
        "search_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("fund", sa.String(length=255)),
        sa.Column("category", sa.String(length=255)),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("excluded_keywords", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("funding_call_id", sa.Integer(), sa.ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("NEW", "UNDER_REVIEW", "INTERESTING", "PARTICIPATE", "REJECTED", "ARCHIVED", name="evaluation_status", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("suitability_score", sa.Integer()),
        sa.Column("suitability_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("suitability_score IS NULL OR (suitability_score >= 0 AND suitability_score <= 100)", name="ck_evaluations_score_range"),
        sa.UniqueConstraint("funding_call_id", name="uq_evaluations_funding_call_id"),
    )
    op.create_table(
        "participations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("funding_call_id", sa.Integer(), sa.ForeignKey("funding_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.Enum("NOT_STARTED", "PLANNING", "PREPARING_APPLICATION", "WAITING_FOR_DECISION", "APPROVED", "REJECTED", "COMPLETED", name="participation_stage", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("responsible_person", sa.String(length=255)),
        sa.Column("notes", sa.Text()),
        sa.Column("next_action", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("funding_call_id", name="uq_participations_funding_call_id"),
    )


def downgrade() -> None:
    op.drop_table("participations")
    op.drop_table("evaluations")
    op.drop_table("search_profiles")
    op.drop_table("funding_calls")
