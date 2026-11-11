"""Photo albums: folders of the kind "album".

Photos are re-encoded on upload (turned the right way up, at most 2560 px,
no EXIF: no location, no camera serial) with a 640 px thumbnail. Members can
be tagged on a photo, untag themselves, or say they don't want to be tagged
at all (which removes their tags). Access is the folder's, like any file.
"""

from __future__ import annotations

import io

from flask import jsonify, request, send_file
from sqlalchemy import func, select

from hubra.core import files as store
from hubra.core.auth.helpers import get_current_member
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.member import Member
from hubra.core.permissions import permission_required
from hubra.core.utils import log_audit

from . import images
from .models import DocumentFile, DocumentFolder, DocumentPhotoOptout, DocumentPhotoTag
from .routes import (
    OWNER,
    Access,
    _actor,
    _clean_name,
    _file_dict,
    _folder_dict,
    _visible_file,
    documents_bp,
    storage_full,
)

MAX_PHOTOS = 20


def tags_of(docs: list[DocumentFile]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    ids = [d.id for d in docs]
    if not ids:
        return out
    for t in db.session.scalars(
        select(DocumentPhotoTag).where(DocumentPhotoTag.file_id.in_(ids))
    ):
        out.setdefault(t.file_id, []).append(t.member_id)
    return out


def tag_dict(doc: DocumentFile, tags: dict, names: dict) -> dict:
    return {
        "caption": doc.description,
        "tags": [{"memberId": m, "name": names.get(m, "?")} for m in tags.get(doc.id, [])],
    }


def opted_out(member_ids) -> set[int]:
    ids = list(set(member_ids))
    if not ids:
        return set()
    return set(
        db.session.scalars(
            select(DocumentPhotoOptout.member_id).where(DocumentPhotoOptout.member_id.in_(ids))
        )
    )


def _covers(albums: list[DocumentFolder]) -> dict[int, int]:
    """Each album's cover: the chosen photo, else its first."""
    out = {a.id: a.cover_file_id for a in albums if a.cover_file_id}
    missing = [a.id for a in albums if a.id not in out]
    if missing:
        for folder_id, file_id in db.session.execute(
            select(DocumentFile.folder_id, func.min(DocumentFile.id))
            .where(DocumentFile.folder_id.in_(missing))
            .where(DocumentFile.thumb_key.is_not(None))
            .group_by(DocumentFile.folder_id)
        ):
            out[folder_id] = file_id
    return out


@documents_bp.get("/albums")
@permission_required("files", "read", "View documents")
def list_albums():
    acc = Access()
    albums = [f for f in acc.folders.values() if f.kind == "album" and acc.can_open(f.id)]
    albums.sort(
        key=lambda f: (f.taken_on or f.created_at.date(), f.id),
        reverse=True,
    )
    counts = dict(
        db.session.execute(
            select(DocumentFile.folder_id, func.count())
            .where(DocumentFile.folder_id.in_([a.id for a in albums] or [0]))
            .group_by(DocumentFile.folder_id)
        ).all()
    )
    covers = _covers(albums)
    out = []
    for a in albums:
        row = _folder_dict(a, counts)
        row["coverFileId"] = covers.get(a.id)
        row["canUpload"] = acc.may_upload(a)
        out.append(row)
    return jsonify({"albums": out, "canManage": acc.manager}), 200


@documents_bp.post("/folders/<int:folder_id>/photos")
@permission_required("files", "read", "View documents")
def upload_photos(folder_id: int):
    acc = Access()
    folder = acc.folders.get(folder_id)
    if folder is None or not acc.can_open(folder_id) or folder.kind != "album":
        return api_error("NOT_FOUND", "no such album", 404)
    if not acc.may_upload(folder):
        return api_error("FORBIDDEN", "you may not add photos to this album", 403)
    if (refused := storage_full()) is not None:
        return refused
    uploads = request.files.getlist("photos")
    if not uploads:
        return api_error("VALIDATION_ERROR", "photos is required", 400)
    if len(uploads) > MAX_PHOTOS:
        return api_error("VALIDATION_ERROR", f"at most {MAX_PHOTOS} photos at once", 400)
    made, failed = [], []
    for f in uploads:
        name = _clean_name(f.filename, 120) or "photo"
        try:
            full, kind, thumb, width, height = images.process(f.read())
            big = store.put(OWNER, full, kind)
            small = store.put(OWNER, thumb, kind)
        except images.BadImage:
            # Fixed texts: exception messages don't go back to the browser.
            failed.append({"name": name, "reason": "not a JPEG, PNG, WebP or GIF photo"})
            continue
        except store.FileTooLarge:
            failed.append({"name": name, "reason": "larger than the club's file limit"})
            continue
        except store.FileStoreError:
            db.session.rollback()
            return api_error("FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503)
        doc = DocumentFile(
            folder_id=folder.id,
            name=name,
            file_key=big.key,
            thumb_key=small.key,
            size=big.size,
            content_type=kind,
            width=width,
            height=height,
            uploaded_by=_actor(acc),
        )
        db.session.add(doc)
        made.append(doc)
    db.session.flush()
    if made:
        log_audit(
            _actor(acc), "documents.photos.add", "DocumentFolder", folder.id, str(len(made))
        )
    db.session.commit()
    return (
        jsonify({"added": [_file_dict(d, acc) for d in made], "failed": failed}),
        201 if made else 400,
    )


@documents_bp.get("/files/<int:file_id>/thumb")
@permission_required("files", "read", "View documents")
def photo_thumb(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None or not doc.thumb_key:
        return api_error("NOT_FOUND", "no such photo", 404)
    try:
        data = store.read(doc.thumb_key)
    except store.FileNotFound:
        return api_error("NOT_FOUND", "the photo is missing from the store", 404)
    except store.FileStoreError:
        return api_error("FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503)
    # The type from the bytes, not the stored one: a thumbnail is only ever
    # an image, whatever the file's content type says.
    kind = images.sniff(data)
    if kind is None:
        return api_error("NOT_FOUND", "no such photo", 404)
    resp = send_file(io.BytesIO(data), mimetype=kind, max_age=86400)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resp


@documents_bp.patch("/photos/<int:file_id>")
@permission_required("files", "read", "View documents")
def update_photo(file_id: int):
    """{caption}: for the uploader too, who may lack the right to write documents."""
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None or not doc.thumb_key:
        return api_error("NOT_FOUND", "no such photo", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    body = request.get_json(silent=True) or {}
    if "caption" in body:
        doc.description = str(body.get("caption") or "").strip()[:500] or None
    db.session.commit()
    return jsonify(_file_dict(doc, acc)), 200


@documents_bp.delete("/photos/<int:file_id>")
@permission_required("files", "read", "View documents")
def delete_photo(file_id: int):
    from .routes import _drop_files

    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None or not doc.thumb_key:
        return api_error("NOT_FOUND", "no such photo", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    folder = acc.folders.get(doc.folder_id) if doc.folder_id else None
    if folder is not None and folder.cover_file_id == doc.id:
        folder.cover_file_id = None
    _drop_files(doc)
    log_audit(_actor(acc), "documents.photo.delete", "DocumentFile", doc.id, doc.name)
    db.session.delete(doc)
    db.session.commit()
    return "", 204


@documents_bp.put("/files/<int:file_id>/tags")
@permission_required("files", "read", "View documents")
def set_tags(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None or not doc.thumb_key:
        return api_error("NOT_FOUND", "no such photo", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    raw = (request.get_json(silent=True) or {}).get("memberIds")
    if (
        not isinstance(raw, list)
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in raw)
        or len(raw) > 100
    ):
        return api_error("VALIDATION_ERROR", "memberIds: a list of member ids", 400)
    wanted = set(raw)
    if opted_out(wanted):
        return api_error(
            "NO_PHOTO_CONSENT", "some of them don't want to be tagged in photos", 409
        )
    found = set(db.session.scalars(select(Member.id).where(Member.id.in_(list(wanted) or [0]))))
    if found != wanted:
        return api_error("VALIDATION_ERROR", "memberIds: no such member", 400)
    existing = {
        t.member_id: t
        for t in db.session.scalars(select(DocumentPhotoTag).where(DocumentPhotoTag.file_id == doc.id))
    }
    for mid, t in existing.items():
        if mid not in wanted:
            db.session.delete(t)
    for mid in wanted - set(existing):
        db.session.add(DocumentPhotoTag(file_id=doc.id, member_id=mid))
    db.session.commit()
    return "", 204


@documents_bp.delete("/files/<int:file_id>/tags/me")
@permission_required("files", "read", "View documents")
def untag_me(file_id: int):
    member = get_current_member()
    tag = db.session.scalar(
        select(DocumentPhotoTag)
        .where(DocumentPhotoTag.file_id == file_id)
        .where(DocumentPhotoTag.member_id == member.id)
    )
    if tag is not None:
        db.session.delete(tag)
        db.session.commit()
    return "", 204


@documents_bp.get("/photo-consent")
@permission_required("files", "read", "View documents")
def get_consent():
    member = get_current_member()
    return jsonify({"photosOfMe": member.id not in opted_out([member.id])}), 200


@documents_bp.put("/photo-consent")
@permission_required("files", "read", "View documents")
def put_consent():
    member = get_current_member()
    allowed = bool((request.get_json(silent=True) or {}).get("allowed"))
    row = db.session.scalar(
        select(DocumentPhotoOptout).where(DocumentPhotoOptout.member_id == member.id)
    )
    if allowed and row is not None:
        db.session.delete(row)
    elif not allowed:
        if row is None:
            db.session.add(DocumentPhotoOptout(member_id=member.id))
        for tag in db.session.scalars(
            select(DocumentPhotoTag).where(DocumentPhotoTag.member_id == member.id)
        ):
            db.session.delete(tag)
    log_audit(member.id, "documents.photo_consent", "Member", member.id, str(allowed))
    db.session.commit()
    return jsonify({"photosOfMe": allowed}), 200
