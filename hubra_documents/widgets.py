"""Dashboard widget of Documents (docs/dashboards.md in hubra-app/hubra).

documents.recent  list  the files changed last, in folders the viewer may open

It reads as the viewing member, who needs ``documents.files.read``.
"""

from __future__ import annotations

from sqlalchemy import select

from hubra.core.extensions import db

from .models import DocumentFile
from .routes import Access


def recent(ctx, config: dict) -> dict:
    try:
        count = max(1, min(int(config.get("count") or 5), 20))
    except (TypeError, ValueError):
        count = 5
    if ctx.actor is None:
        return {"items": [], "total": 0}
    acc = Access(ctx.actor)
    items = []
    for doc in db.session.scalars(
        select(DocumentFile).order_by(DocumentFile.updated_at.desc()).limit(200)
    ):
        if not acc.can_open(doc.folder_id):
            continue
        folder = acc.folders.get(doc.folder_id) if doc.folder_id else None
        when = f"{doc.updated_at:%d.%m.%Y}" if doc.updated_at else None
        sub = " · ".join(p for p in (folder.name if folder else None, when) if p)
        path = f"/app/documents/{doc.folder_id}" if doc.folder_id else "/app/documents"
        items.append({"label": doc.name, "sub": sub or None, "path": path})
        if len(items) == count:
            break
    return {"items": items}
