"""Folders and files, photo albums and their photos (one copy per club schema).

A photo album is a folder of the kind "album": the same access per role and
group, its files are photos with a thumbnail and the members shown on them.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from hubra.core.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentFolder(db.Model):
    __tablename__ = "documents_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents_folders.id", ondelete="CASCADE"), nullable=True
    )
    # Empty lists: open to everyone who may read documents. Otherwise only to
    # members holding one of these roles or in one of these groups.
    role_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    group_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # "files", or "album": a photo album (Fotos), shown as a grid.
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="files")
    taken_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Album: every member who may open it adds photos, not only writers.
    members_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cover_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Where it came from when taken over ("community.album:12"), so a
    # take-over that runs twice doesn't copy it twice.
    source: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)


class DocumentFile(db.Model):
    __tablename__ = "documents_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents_folders.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The key in Hubra's file store (stored_files.key).
    file_key: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(
        String(255), nullable=False, default="application/octet-stream"
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    # Photos in an album: re-encoded without EXIF, plus a thumbnail.
    thumb_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)


class DocumentPhotoTag(db.Model):
    """A member shown on a photo."""

    __tablename__ = "documents_photo_tags"
    __table_args__ = (UniqueConstraint("file_id", "member_id", name="uq_documents_photo_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )


class DocumentPhotoOptout(db.Model):
    """A member who doesn't want to be tagged in photos."""

    __tablename__ = "documents_photo_optouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
