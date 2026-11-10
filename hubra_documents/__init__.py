"""Documents: the club's document library.

Folders (nested) hold files. A folder is open to every member who may read
documents, or only to the roles and groups it names; a subfolder is only
open to whoever may open its parent too. The files themselves are kept in
Hubra's file store (``hubra.core.files``): encrypted with the club's key, in
the platform's S3 bucket or on the server.

Permissions:
    documents.files.read     see the library (the folders open to them)
    documents.files.write    upload, and rename or delete their own files
    documents.folders.manage folders and their access, every file, every folder
"""

from hubra.core.contracts import WidgetField, widget_contract
from hubra.core.modules import Blueprint, Module, NavItem

module = Module(
    code="documents",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    role_defaults={"board": "edit", "secretary": "all"},
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
    tables=("documents_folders", "documents_files"),
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
