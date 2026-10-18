"""Join the notification and application-draft migration branches.

Revision ID: 0010_merge_notification_and_application_drafts
Revises: 0009_notification_outbox, 0009_draft_compatibility
"""

revision = "0010_merge_notification_and_application_drafts"
down_revision = ("0009_notification_outbox", "0009_draft_compatibility")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The existing branches already apply all schema changes."""


def downgrade() -> None:
    """The merge revision has no schema changes to reverse."""
