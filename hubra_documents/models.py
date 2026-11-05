"""Folders and files (one copy per club schema)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
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
