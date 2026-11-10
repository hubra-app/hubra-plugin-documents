"""photo albums: album folders, photo files, tags and opt-outs

Photo albums move here from the Community plugin. An album is a folder of
the kind "album"; its files are photos with a thumbnail.

Revision ID: 5a1d8e3c7b92
Revises: 7c2e5a9d1f30
Create Date: 2026-11-10 14:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import columns, has_table

revision = "5a1d8e3c7b92"
down_revision = "7c2e5a9d1f30"
branch_labels = None
depends_on = None


def upgrade():
    have = columns("documents_folders")
    with op.batch_alter_table("documents_folders", schema=None) as batch_op:
        if "kind" not in have:
            batch_op.add_column(
                sa.Column("kind", sa.String(10), nullable=False, server_default="files")
            )
        if "taken_on" not in have:
            batch_op.add_column(sa.Column("taken_on", sa.Date(), nullable=True))
        if "members_upload" not in have:
            batch_op.add_column(
                sa.Column("members_upload", sa.Boolean(), nullable=False, server_default=sa.true())
            )
        if "cover_file_id" not in have:
            batch_op.add_column(sa.Column("cover_file_id", sa.Integer(), nullable=True))
        if "source" not in have:
            batch_op.add_column(sa.Column("source", sa.String(60), nullable=True))
            batch_op.create_index("ix_documents_folders_source", ["source"])
    have = columns("documents_files")
    with op.batch_alter_table("documents_files", schema=None) as batch_op:
        if "thumb_key" not in have:
            batch_op.add_column(sa.Column("thumb_key", sa.String(255), nullable=True))
        if "width" not in have:
            batch_op.add_column(sa.Column("width", sa.Integer(), nullable=True))
        if "height" not in have:
            batch_op.add_column(sa.Column("height", sa.Integer(), nullable=True))
        if "source" not in have:
            batch_op.add_column(sa.Column("source", sa.String(60), nullable=True))
            batch_op.create_index("ix_documents_files_source", ["source"])
    if not has_table("documents_photo_tags"):
        op.create_table(
            "documents_photo_tags",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["file_id"], ["documents_files.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("file_id", "member_id", name="uq_documents_photo_tag"),
        )
        op.create_index("ix_documents_photo_tags_file_id", "documents_photo_tags", ["file_id"])
    if not has_table("documents_photo_optouts"):
        op.create_table(
            "documents_photo_optouts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("member_id"),
        )


def downgrade():
    op.drop_table("documents_photo_optouts")
    op.drop_index("ix_documents_photo_tags_file_id", table_name="documents_photo_tags")
    op.drop_table("documents_photo_tags")
    with op.batch_alter_table("documents_files", schema=None) as batch_op:
        batch_op.drop_index("ix_documents_files_source")
        for col in ("source", "height", "width", "thumb_key"):
            batch_op.drop_column(col)
    with op.batch_alter_table("documents_folders", schema=None) as batch_op:
        batch_op.drop_index("ix_documents_folders_source")
        for col in ("source", "cover_file_id", "members_upload", "taken_on", "kind"):
            batch_op.drop_column(col)
