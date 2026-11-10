"""Documents: the club's document library.

Folders (nested) hold files. A folder is open to every member who may read
documents, or only to the roles and groups it names; a subfolder is only
open to whoever may open its parent too. The files themselves are kept in
Hubra's file store (``hubra.core.files``): encrypted with the club's key, in
the platform's S3 bucket or on the server.

Photo albums are folders of the kind "album" (Fotos): photos re-encoded
without EXIF, with thumbnails, members tagged on them, and "no photos of
me". They move in from the Community plugin (job documents-take-over-albums,
through Community's contracts).

Permissions:
    documents.files.read     see the library (the folders open to them)
    documents.files.write    upload, and rename or delete their own files
    documents.folders.manage folders and their access, every file, every folder
"""

from hubra.core.contracts import WidgetField, widget_contract
from hubra.core.modules import Blueprint, Module, NavItem, Schedule

module = Module(
    code="documents",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    # Members see the folders open to everyone and the photo albums.
    role_defaults={"member": "view", "board": "edit", "secretary": "all"},
    name="Documents",
    description="Document library with folders and access per role or group",
    default_enabled=False,
    depends_on=("members",),
    blueprints=(
        Blueprint(
            "hubra_documents.routes",
            "documents_bp",
            "/api/v1/app/documents",
        ),
    ),
    nav=(
        NavItem(
            "/app/documents",
            "shell.nav.documents",
            "folders",
            section="operations",
            order=40,
            perms=("documents.files.read",),
        ),
    ),
    tables=(
        "documents_folders",
        "documents_files",
        "documents_photo_tags",
        "documents_photo_optouts",
    ),
    tasks=("hubra_documents.tasks",),
    schedule=(
        # Until Community's albums are all here; a no-op without them.
        Schedule("documents-take-over-albums", "hubra_documents.tasks.take_over_albums", 600.0),
    ),
    # Optional: the Community plugin's albums move in (hubra_documents/takeover.py).
    consumes={
        "community.albums.export": ">=1,<2",
        "community.photos.optouts": ">=1,<2",
    },
    # Dashboard widget (hubra_documents/widgets.py).
    provides=(
        widget_contract(
            "documents.recent",
            "hubra_documents.widgets:recent",
            label="documents.widget.recent",
            description="documents.widget.recentHint",
            size="m",
            view="list",
            perm="documents.files.read",
            fields=(WidgetField("count", "documents.widget.count", "number", 5),),
        ),
    ),
)
