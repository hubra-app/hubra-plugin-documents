"""documents_folders and documents_files

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_documents). has_table() keeps it safe to run twice.

Revision ID: 7c2e5a9d1f30
Revises:
Create Date: 2026-11-05 09:30:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "7c2e5a9d1f30"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if not has_table("documents_folders"):
        op.create_table(
            "documents_folders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("role_ids", sa.JSON(), nullable=False),
            sa.Column("group_ids", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["parent_id"], ["documents_folders.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["created_by"], ["members.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("documents_files"):
        op.create_table(
            "documents_files",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("folder_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("file_key", sa.String(255), nullable=False),
            sa.Column("size", sa.BigInteger(), nullable=False),
            sa.Column("content_type", sa.String(255), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["folder_id"], ["documents_folders.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["uploaded_by"], ["members.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_documents_files_folder_id", "documents_files", ["folder_id"]
        )


def downgrade():
    op.drop_index("ix_documents_files_folder_id", table_name="documents_files")
    op.drop_table("documents_files")
    op.drop_table("documents_folders")
