"""Photo albums from the Community plugin move in here.

Read through Community's queries ``community.albums.export`` and
``community.photos.optouts``, never its tables. Each album becomes a folder
of the kind "album" (open to every reader, like the gallery was), each photo
a file here: its bytes are copied in Hubra's file store, so the album stays
when Community is uninstalled. Tags and "no photos of me" come along. Each
album and photo is taken once (``source``), so the job can run every few
minutes until Community's gallery is gone; Community leaves its own copy
alone.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from hubra.core import files as store
from hubra.core.contracts import SYSTEM, ActionUnavailable, available, query
from hubra.core.extensions import db
from hubra.core.models.member import Member

from .models import DocumentFile, DocumentFolder, DocumentPhotoOptout, DocumentPhotoTag
from .routes import OWNER

log = logging.getLogger(__name__)

ALBUMS = "community.albums.export"
OPTOUTS = "community.photos.optouts"


def _copy(key: str | None, content_type: str) -> tuple[str, int] | None:
    if not key:
        return None
    try:
        data = store.read(key)
    except store.FileNotFound:
        return None
    stored = store.put(OWNER, data, content_type)
    return stored.key, stored.size


def _members(ids) -> set[int]:
    ids = {i for i in ids if i}
    if not ids:
        return set()
    return set(db.session.scalars(select(Member.id).where(Member.id.in_(ids))))


def take_over_optouts() -> int:
    if not available(OPTOUTS):
        return 0
    have = set(db.session.scalars(select(DocumentPhotoOptout.member_id)))
    wanted = {o["member_id"] for o in query(OPTOUTS, actor=SYSTEM)} - have
    for mid in _members(wanted):
        db.session.add(DocumentPhotoOptout(member_id=mid))
    db.session.flush()
    return len(wanted)


def take_over_albums(limit: int = 20) -> dict:
    """Copy albums not taken yet. Returns how many albums and photos came."""
    done = {"albums": 0, "photos": 0}
    if not available(ALBUMS):
        return done
    take_over_optouts()
    refused = set(db.session.scalars(select(DocumentPhotoOptout.member_id)))
    after = 0
    while True:
        try:
            batch = query(ALBUMS, after_id=after, limit=limit, actor=SYSTEM)
        except ActionUnavailable:
            break
        if not batch:
            break
        for album in batch:
            after = max(after, album["id"])
            done["photos"] += _take_album(album, refused, done)
        db.session.flush()
    return done


def _take_album(album: dict, refused: set[int], done: dict) -> int:
    source = f"community.album:{album['id']}"
    folder = db.session.scalar(select(DocumentFolder).where(DocumentFolder.source == source))
    if folder is None:
        from datetime import date, datetime

        creator = album.get("created_by")
        folder = DocumentFolder(
            name=album["title"][:120],
            description=album.get("description"),
            kind="album",
            taken_on=date.fromisoformat(album["taken_on"]) if album.get("taken_on") else None,
            members_upload=bool(album.get("members_upload", True)),
            created_by=creator if _members([creator]) else None,
            created_at=datetime.fromisoformat(album["created_at"]),
            role_ids=[],
            group_ids=[],
            source=source,
        )
        db.session.add(folder)
        db.session.flush()
        done["albums"] += 1
    taken = set(
        db.session.scalars(
            select(DocumentFile.source).where(DocumentFile.folder_id == folder.id)
        )
    )
    uploaders = _members(p.get("uploaded_by") for p in album["photos"])
    count = 0
    for photo in album["photos"]:
        psource = f"community.photo:{photo['id']}"
        if psource in taken:
            continue
        from datetime import datetime

        full = _copy(photo["file_key"], photo["content_type"])
        if full is None:
            log.warning("documents: photo %s has no file, skipped", photo["id"])
            continue
        thumb = _copy(photo.get("thumb_key"), photo["content_type"]) or full
        doc = DocumentFile(
            folder_id=folder.id,
            name=f"Foto {photo['id']}",
            description=photo.get("caption"),
            file_key=full[0],
            thumb_key=thumb[0],
            size=full[1],
            content_type=photo["content_type"],
            width=photo.get("width"),
            height=photo.get("height"),
            uploaded_by=photo.get("uploaded_by") if photo.get("uploaded_by") in uploaders else None,
            created_at=datetime.fromisoformat(photo["created_at"]),
            source=psource,
        )
        db.session.add(doc)
        db.session.flush()
        for mid in _members(set(photo.get("tags") or []) - refused):
            db.session.add(DocumentPhotoTag(file_id=doc.id, member_id=mid))
        if album.get("cover_photo_id") == photo["id"]:
            folder.cover_file_id = doc.id
        count += 1
    return count
