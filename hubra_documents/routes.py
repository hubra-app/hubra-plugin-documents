"""Documents API: /api/v1/app/documents.

GET    /library                     folders open to me + files at the top level
GET    /folders/<id>                one folder: its subfolders and files
POST   /folders                     {name, parentId?, description?, roleIds?, groupIds?}
PATCH  /folders/<id>                same fields
DELETE /folders/<id>                only an empty folder
GET    /files?q=                    search the files open to me
POST   /files                       multipart: file, folderId?, description?
PATCH  /files/<id>                  {name?, description?, folderId?}
PUT    /files/<id>/content          multipart: file (a new version replaces the old)
GET    /files/<id>/download[?inline=1]
DELETE /files/<id>
GET    /access-options              roles and groups to choose from
"""

from __future__ import annotations

import io
import os
import re

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import func, select

from hubra.core.auth.helpers import get_current_member
from hubra.core.permissions import member_has_permission, permission_required
from hubra.core.utils import log_audit
from hubra.core import files as store
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.group import Group, GroupMembership
from hubra.core.models.role import Role

from .models import DocumentFile, DocumentFolder

documents_bp = Blueprint("documents_bp", __name__)

OWNER = "documents"
MANAGE = "documents.folders.manage"
# Shown in the browser only these; anything else (HTML, SVG …) downloads.
INLINE_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
}


# ── Access ───────────────────────────────────────────────────────────────────


class Access:
    """What the signed-in member may open, worked out once per request."""

    def __init__(self, member=None) -> None:
        self.member = member if member is not None else get_current_member()
        self.manager = member_has_permission(self.member, MANAGE)
        self.writer = self.manager or member_has_permission(
            self.member, "documents.files.write"
        )
        self.role_ids = {r.id for r in (self.member.roles if self.member else [])}
        self.group_ids = (
            set(
                db.session.scalars(
                    select(GroupMembership.group_id).where(
                        GroupMembership.member_id == self.member.id
                    )
                )
            )
            if self.member
            else set()
        )
        self.folders = {f.id: f for f in db.session.scalars(select(DocumentFolder))}
        self._open: dict[int, bool] = {}

    def _allows(self, folder: DocumentFolder) -> bool:
        roles, groups = set(folder.role_ids or []), set(folder.group_ids or [])
        if not roles and not groups:
            return True
        return bool(roles & self.role_ids or groups & self.group_ids)

    def can_open(self, folder_id: int | None) -> bool:
        """The folder and every folder above it let me in (top level: yes)."""
        if folder_id is None or self.manager:
            return folder_id is None or folder_id in self.folders
        if folder_id not in self._open:
            folder = self.folders.get(folder_id)
            self._open[folder_id] = bool(
                folder and self._allows(folder) and self.can_open(folder.parent_id)
            )
        return self._open[folder_id]

    def may_change(self, doc: DocumentFile) -> bool:
        if self.manager:
            return True
        return bool(self.writer and self.member and doc.uploaded_by == self.member.id)


def _folder_dict(f: DocumentFolder, counts: dict[int, int] | None = None) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "description": f.description,
        "parentId": f.parent_id,
        "roleIds": list(f.role_ids or []),
        "groupIds": list(f.group_ids or []),
        "restricted": bool(f.role_ids or f.group_ids),
        "fileCount": (counts or {}).get(f.id, 0),
    }


def _file_dict(
    d: DocumentFile, acc: Access, names: dict[int, str] | None = None
) -> dict:
    return {
        "id": d.id,
        "folderId": d.folder_id,
        "name": d.name,
        "description": d.description,
        "size": d.size,
        "contentType": d.content_type,
        "uploadedBy": d.uploaded_by,
        "uploadedByName": (names or {}).get(d.uploaded_by) if d.uploaded_by else None,
        "createdAt": d.created_at.isoformat() if d.created_at else None,
        "updatedAt": d.updated_at.isoformat() if d.updated_at else None,
        "canChange": acc.may_change(d),
    }


def _actor(acc: Access) -> int | None:
    return acc.member.id if acc.member else None


def _member_names(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    from hubra.core.models.member import Member

    return {
        m.id: m.name
        for m in db.session.scalars(select(Member).where(Member.id.in_(ids)))
    }


def _counts() -> dict[int, int]:
    rows = db.session.execute(
        select(DocumentFile.folder_id, func.count()).group_by(DocumentFile.folder_id)
    )
    return {fid: n for fid, n in rows if fid is not None}


# ── Input ────────────────────────────────────────────────────────────────────


def _clean_name(raw: str, limit: int) -> str:
    name = re.sub(
        r"[\x00-\x1f\x7f]", "", os.path.basename(str(raw or "").replace("\\", "/"))
    )
    return name.strip()[:limit]


def _ids(value, known: set[int]) -> list[int] | None:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
        return None
    return sorted({v for v in value if v in known})


def _folder_fields(body: dict, folder: DocumentFolder | None, acc: Access):
    """Apply {name, description, parentId, roleIds, groupIds} to *folder* (a
    new one when None); returns the folder, or an error response."""
    target = folder or DocumentFolder()
    if "name" in body or folder is None:
        name = _clean_name(body.get("name"), 120)
        if not name:
            return api_error("VALIDATION_ERROR", "name is required", 400)
        target.name = name
    if "description" in body:
        target.description = str(body.get("description") or "").strip() or None
    if "parentId" in body:
        parent_id = body.get("parentId")
        if parent_id is not None:
            if not isinstance(parent_id, int) or parent_id not in acc.folders:
                return api_error("VALIDATION_ERROR", "parentId: no such folder", 400)
            # No folder inside itself or inside one of its own subfolders.
            walk = parent_id
            while folder is not None and walk is not None:
                if walk == folder.id:
                    return api_error("VALIDATION_ERROR", "parentId: inside itself", 400)
                walk = acc.folders[walk].parent_id
        target.parent_id = parent_id
    known = {
        "roleIds": set(db.session.scalars(select(Role.id))),
        "groupIds": set(db.session.scalars(select(Group.id))),
    }
    for key, attr in (("roleIds", "role_ids"), ("groupIds", "group_ids")):
        if key in body or folder is None:
            ids = _ids(body.get(key), known[key])
            if ids is None:
                return api_error("VALIDATION_ERROR", f"{key}: a list of ids", 400)
            setattr(target, attr, ids)
    return target


def _upload():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return None, api_error("VALIDATION_ERROR", "file is required", 400)
    data = upload.read()
    if not data:
        return None, api_error("VALIDATION_ERROR", "the file is empty", 400)
    try:
        stored = store.put(OWNER, data, upload.mimetype or "application/octet-stream")
    except store.FileTooLarge as err:
        return None, api_error("FILE_TOO_LARGE", str(err), 413)
    except store.FileStoreError:
        return None, api_error(
            "FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503
        )
    return (stored, _clean_name(upload.filename, 255) or "file"), None


# ── Library and folders ──────────────────────────────────────────────────────


@documents_bp.get("/library")
@permission_required("files", "read", "View documents")
def library():
    acc = Access()
    counts = _counts()
    folders = [
        _folder_dict(f, counts)
        for f in sorted(acc.folders.values(), key=lambda f: f.name.lower())
        if acc.can_open(f.id)
    ]
    top = list(
        db.session.scalars(
            select(DocumentFile)
            .where(DocumentFile.folder_id.is_(None))
            .order_by(func.lower(DocumentFile.name))
        )
    )
    names = _member_names({d.uploaded_by for d in top if d.uploaded_by})
    return jsonify(
        {
            "folders": folders,
            "files": [_file_dict(d, acc, names) for d in top],
            "canWrite": acc.writer,
            "canManage": acc.manager,
        }
    ), 200


@documents_bp.get("/folders/<int:folder_id>")
@permission_required("files", "read", "View documents")
def get_folder(folder_id: int):
    acc = Access()
    if not acc.can_open(folder_id):
        return api_error("NOT_FOUND", "no such folder", 404)
    counts = _counts()
    folder = acc.folders[folder_id]
    docs = list(
        db.session.scalars(
            select(DocumentFile)
            .where(DocumentFile.folder_id == folder_id)
            .order_by(func.lower(DocumentFile.name))
        )
    )
    names = _member_names({d.uploaded_by for d in docs if d.uploaded_by})
    path = []
    walk = folder.parent_id
    while walk is not None:
        path.insert(0, {"id": walk, "name": acc.folders[walk].name})
        walk = acc.folders[walk].parent_id
    return jsonify(
        {
            "folder": _folder_dict(folder, counts),
            "path": path,
            "folders": [
                _folder_dict(f, counts)
                for f in sorted(acc.folders.values(), key=lambda f: f.name.lower())
                if f.parent_id == folder_id and acc.can_open(f.id)
            ],
            "files": [_file_dict(d, acc, names) for d in docs],
            "canWrite": acc.writer,
            "canManage": acc.manager,
        }
    ), 200


@documents_bp.post("/folders")
@permission_required("folders", "manage", "Manage folders and access")
def create_folder():
    acc = Access()
    result = _folder_fields(request.get_json(silent=True) or {}, None, acc)
    if not isinstance(result, DocumentFolder):
        return result
    result.created_by = acc.member.id if acc.member else None
    db.session.add(result)
    db.session.flush()
    log_audit(
        _actor(acc), "documents.folder.create", "DocumentFolder", result.id, result.name
    )
    db.session.commit()
    return jsonify(_folder_dict(result)), 201


@documents_bp.patch("/folders/<int:folder_id>")
@permission_required("folders", "manage", "Manage folders and access")
def update_folder(folder_id: int):
    acc = Access()
    folder = acc.folders.get(folder_id)
    if folder is None:
        return api_error("NOT_FOUND", "no such folder", 404)
    result = _folder_fields(request.get_json(silent=True) or {}, folder, acc)
    if not isinstance(result, DocumentFolder):
        return result
    log_audit(
        _actor(acc), "documents.folder.update", "DocumentFolder", folder.id, folder.name
    )
    db.session.commit()
    return jsonify(_folder_dict(folder, _counts())), 200


@documents_bp.delete("/folders/<int:folder_id>")
@permission_required("folders", "manage", "Manage folders and access")
def delete_folder(folder_id: int):
    acc = Access()
    folder = acc.folders.get(folder_id)
    if folder is None:
        return api_error("NOT_FOUND", "no such folder", 404)
    has_files = db.session.scalar(
        select(func.count())
        .select_from(DocumentFile)
        .where(DocumentFile.folder_id == folder_id)
    )
    if has_files or any(f.parent_id == folder_id for f in acc.folders.values()):
        return api_error("FOLDER_NOT_EMPTY", "move or delete what is in it first", 409)
    log_audit(
        _actor(acc), "documents.folder.delete", "DocumentFolder", folder.id, folder.name
    )
    db.session.delete(folder)
    db.session.commit()
    return "", 204


@documents_bp.get("/access-options")
@permission_required("folders", "manage", "Manage folders and access")
def access_options():
    roles = db.session.scalars(select(Role).order_by(Role.name))
    groups = db.session.scalars(select(Group).order_by(Group.name))
    return jsonify(
        {
            "roles": [{"id": r.id, "name": r.name} for r in roles],
            "groups": [{"id": g.id, "name": g.name} for g in groups],
        }
    ), 200


# ── Files ────────────────────────────────────────────────────────────────────


def _visible_file(file_id: int, acc: Access) -> DocumentFile | None:
    doc = db.session.get(DocumentFile, file_id)
    if doc is None or not acc.can_open(doc.folder_id):
        return None
    return doc


@documents_bp.get("/files")
@permission_required("files", "read", "View documents")
def search_files():
    acc = Access()
    q = str(request.args.get("q") or "").strip()
    stmt = select(DocumentFile).order_by(DocumentFile.updated_at.desc()).limit(500)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(DocumentFile.name).like(like)
            | func.lower(func.coalesce(DocumentFile.description, "")).like(like)
        )
    docs = [d for d in db.session.scalars(stmt) if acc.can_open(d.folder_id)][:100]
    names = _member_names({d.uploaded_by for d in docs if d.uploaded_by})
    folder_names = {fid: f.name for fid, f in acc.folders.items()}
    out = []
    for d in docs:
        row = _file_dict(d, acc, names)
        row["folderName"] = folder_names.get(d.folder_id) if d.folder_id else None
        out.append(row)
    return jsonify(out), 200


@documents_bp.post("/files")
@permission_required("files", "write", "Upload documents")
def upload_file():
    acc = Access()
    folder_id = request.form.get("folderId")
    folder_id = int(folder_id) if folder_id and folder_id.isdigit() else None
    if folder_id is not None and not acc.can_open(folder_id):
        return api_error("NOT_FOUND", "no such folder", 404)
    uploaded, error = _upload()
    if error:
        return error
    stored, name = uploaded
    doc = DocumentFile(
        folder_id=folder_id,
        name=name,
        description=(request.form.get("description") or "").strip() or None,
        file_key=stored.key,
        size=stored.size,
        content_type=stored.content_type,
        uploaded_by=acc.member.id if acc.member else None,
    )
    db.session.add(doc)
    db.session.flush()
    log_audit(_actor(acc), "documents.file.upload", "DocumentFile", doc.id, doc.name)
    db.session.commit()
    return jsonify(_file_dict(doc, acc)), 201


@documents_bp.put("/files/<int:file_id>/content")
@permission_required("files", "write", "Upload documents")
def replace_file(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None:
        return api_error("NOT_FOUND", "no such file", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    uploaded, error = _upload()
    if error:
        return error
    stored, _name = uploaded
    old_key = doc.file_key
    doc.file_key, doc.size, doc.content_type = (
        stored.key,
        stored.size,
        stored.content_type,
    )
    try:
        store.remove(old_key)
    except store.FileNotFound:
        pass
    log_audit(_actor(acc), "documents.file.replace", "DocumentFile", doc.id, doc.name)
    db.session.commit()
    return jsonify(_file_dict(doc, acc)), 200


@documents_bp.patch("/files/<int:file_id>")
@permission_required("files", "write", "Upload documents")
def update_file(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None:
        return api_error("NOT_FOUND", "no such file", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    body = request.get_json(silent=True) or {}
    if "name" in body:
        name = _clean_name(body.get("name"), 255)
        if not name:
            return api_error("VALIDATION_ERROR", "name is required", 400)
        doc.name = name
    if "description" in body:
        doc.description = str(body.get("description") or "").strip() or None
    if "folderId" in body:
        target = body.get("folderId")
        if target is not None and (
            not isinstance(target, int) or not acc.can_open(target)
        ):
            return api_error("VALIDATION_ERROR", "folderId: no such folder", 400)
        doc.folder_id = target
    log_audit(_actor(acc), "documents.file.update", "DocumentFile", doc.id, doc.name)
    db.session.commit()
    return jsonify(_file_dict(doc, acc)), 200


@documents_bp.get("/files/<int:file_id>/download")
@permission_required("files", "read", "View documents")
def download_file(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None:
        return api_error("NOT_FOUND", "no such file", 404)
    try:
        data = store.read(doc.file_key)
    except store.FileNotFound:
        return api_error("NOT_FOUND", "the file is missing from the store", 404)
    except store.FileStoreError:
        return api_error(
            "FILE_STORE_UNAVAILABLE", "the file store is not reachable", 503
        )
    inline = request.args.get("inline") == "1" and doc.content_type in INLINE_TYPES
    resp = send_file(
        io.BytesIO(data),
        mimetype=doc.content_type if inline else "application/octet-stream",
        as_attachment=not inline,
        download_name=doc.name,
        max_age=0,
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store"
    if inline:
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
        )
    return resp


@documents_bp.delete("/files/<int:file_id>")
@permission_required("files", "write", "Upload documents")
def delete_file(file_id: int):
    acc = Access()
    doc = _visible_file(file_id, acc)
    if doc is None:
        return api_error("NOT_FOUND", "no such file", 404)
    if not acc.may_change(doc):
        return api_error("FORBIDDEN", "only the uploader or a folder manager", 403)
    try:
        store.remove(doc.file_key)
    except store.FileNotFound:
        pass
    log_audit(_actor(acc), "documents.file.delete", "DocumentFile", doc.id, doc.name)
    db.session.delete(doc)
    db.session.commit()
    return "", 204
