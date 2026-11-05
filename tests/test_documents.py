"""The document library: folders, access per role or group, uploads.

Runs with Hubra's fixtures once the plugin is in plugins/documents of a
Hubra checkout (see README.md).
"""

from __future__ import annotations

import io

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/documents"
READ = ["documents.files.read"]
WRITE = ["documents.files.read", "documents.files.write"]


def _upload(
    client,
    name="Protokoll.pdf",
    data=b"%PDF-1.4 GV",
    folder=None,
    ctype="application/pdf",
):
    form = {"file": (io.BytesIO(data), name, ctype)}
    if folder is not None:
        form["folderId"] = str(folder)
    return client.post(f"{BASE}/files", data=form, content_type="multipart/form-data")


@pytest.fixture
def lib(client, app, db, seeded_db):
    """Admin plus Rita (read), Will (write) and Vera (read, in group Vorstand).
    Folders: Allgemein (open), Vorstand (group Vorstand only) with a
    subfolder Finanzen, Archiv (role of Rita only)."""
    from hubra.core.models.group import Group, GroupMembership

    set_modules(True, "documents")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    rita = _make_role_and_member(db, tier, name="Rita", permission_keys=READ)
    _make_role_and_member(db, tier, name="Will", permission_keys=WRITE)
    vera = _make_role_and_member(db, tier, name="Vera", permission_keys=READ)
    board = Group(name="Vorstand")
    db.session.add(board)
    db.session.flush()
    db.session.add(GroupMembership(group_id=board.id, member_id=vera.id))
    db.session.commit()

    _login(client, "admin@test.ch")
    allg = client.post(f"{BASE}/folders", json={"name": "Allgemein"}).get_json()
    vorstand = client.post(
        f"{BASE}/folders", json={"name": "Vorstand", "groupIds": [board.id]}
    ).get_json()
    finanzen = client.post(
        f"{BASE}/folders", json={"name": "Finanzen", "parentId": vorstand["id"]}
    ).get_json()
    archiv = client.post(
        f"{BASE}/folders", json={"name": "Archiv", "roleIds": [rita.roles[0].id]}
    ).get_json()
    secret = _upload(client, "Budget.pdf", folder=finanzen["id"]).get_json()
    return {
        "allg": allg["id"],
        "vorstand": vorstand["id"],
        "finanzen": finanzen["id"],
        "archiv": archiv["id"],
        "secret": secret["id"],
        "board": board.id,
    }


def _names(client):
    return sorted(
        f["name"] for f in client.get(f"{BASE}/library").get_json()["folders"]
    )


def test_admin_sees_every_folder(client, lib):
    assert _names(client) == ["Allgemein", "Archiv", "Finanzen", "Vorstand"]


def test_folders_follow_roles_and_groups(client, lib):
    _login(client, "rita@test.ch")
    assert _names(client) == ["Allgemein", "Archiv"]
    _login(client, "vera@test.ch")
    # Finanzen has no list of its own, but sits inside Vorstand.
    assert _names(client) == ["Allgemein", "Finanzen", "Vorstand"]
    _login(client, "will@test.ch")
    assert _names(client) == ["Allgemein"]


def test_a_closed_folder_and_its_files_are_not_found(client, lib):
    _login(client, "rita@test.ch")
    assert client.get(f"{BASE}/folders/{lib['finanzen']}").status_code == 404
    assert client.get(f"{BASE}/files/{lib['secret']}/download").status_code == 404
    assert [f["name"] for f in client.get(f"{BASE}/files?q=budget").get_json()] == []
    _login(client, "vera@test.ch")
    assert [f["name"] for f in client.get(f"{BASE}/files?q=budget").get_json()] == [
        "Budget.pdf"
    ]
    got = client.get(f"{BASE}/files/{lib['secret']}/download")
    assert got.status_code == 200 and got.data == b"%PDF-1.4 GV"


def test_upload_download_round_trip(client, lib):
    _login(client, "will@test.ch")
    up = _upload(client, "../../Statuten.pdf", b"%PDF statuten", folder=lib["allg"])
    assert up.status_code == 201
    doc = up.get_json()
    assert doc["name"] == "Statuten.pdf" and doc["size"] == len(b"%PDF statuten")
    assert doc["canChange"] is True

    got = client.get(f"{BASE}/files/{doc['id']}/download")
    assert got.data == b"%PDF statuten"
    assert got.headers["Content-Type"] == "application/octet-stream"
    assert "attachment" in got.headers["Content-Disposition"]
    inline = client.get(f"{BASE}/files/{doc['id']}/download?inline=1")
    assert inline.headers["Content-Type"] == "application/pdf"
    assert "sandbox" in inline.headers["Content-Security-Policy"]

    folder = client.get(f"{BASE}/folders/{lib['allg']}").get_json()
    assert [f["name"] for f in folder["files"]] == ["Statuten.pdf"]


def test_html_is_never_shown_inline(client, lib):
    _login(client, "will@test.ch")
    doc = _upload(
        client, "x.html", b"<script>alert(1)</script>", ctype="text/html"
    ).get_json()
    got = client.get(f"{BASE}/files/{doc['id']}/download?inline=1")
    assert got.headers["Content-Type"] == "application/octet-stream"
    assert "attachment" in got.headers["Content-Disposition"]


def test_only_the_uploader_or_a_manager_changes_a_file(client, lib, db, seeded_db):
    _make_role_and_member(db, seeded_db["tier"], name="Wanda", permission_keys=WRITE)
    _login(client, "will@test.ch")
    doc = _upload(client, "Plan.pdf", folder=lib["allg"]).get_json()

    _login(client, "wanda@test.ch")
    assert (
        client.patch(f"{BASE}/files/{doc['id']}", json={"name": "Mine.pdf"}).status_code
        == 403
    )
    assert client.delete(f"{BASE}/files/{doc['id']}").status_code == 403

    _login(client, "will@test.ch")
    r = client.patch(f"{BASE}/files/{doc['id']}", json={"name": "Plan 2026.pdf"})
    assert r.status_code == 200 and r.get_json()["name"] == "Plan 2026.pdf"
    # Moving into a folder Will can't open is refused.
    r = client.patch(f"{BASE}/files/{doc['id']}", json={"folderId": lib["vorstand"]})
    assert r.status_code == 400

    _login(client, "admin@test.ch")
    assert client.delete(f"{BASE}/files/{doc['id']}").status_code == 204
    assert client.get(f"{BASE}/files/{doc['id']}/download").status_code == 404


def test_a_new_version_replaces_the_old(client, lib):
    from hubra.core.models.stored_file import StoredFile
    from hubra.core.extensions import db

    _login(client, "will@test.ch")
    doc = _upload(client, "Liste.pdf", b"v1").get_json()
    form = {"file": (io.BytesIO(b"version 2"), "Liste-neu.pdf", "application/pdf")}
    r = client.put(
        f"{BASE}/files/{doc['id']}/content",
        data=form,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200 and r.get_json()["size"] == len(b"version 2")
    assert client.get(f"{BASE}/files/{doc['id']}/download").data == b"version 2"
    assert (
        db.session.query(StoredFile).filter_by(owner="documents", size=2).count() == 0
    )


def test_readers_cannot_upload_or_manage(client, lib):
    _login(client, "rita@test.ch")
    assert _upload(client).status_code == 403
    assert client.post(f"{BASE}/folders", json={"name": "Mine"}).status_code == 403
    _login(client, "will@test.ch")
    assert client.post(f"{BASE}/folders", json={"name": "Mine"}).status_code == 403
    assert _upload(client, folder=lib["vorstand"]).status_code == 404


def test_folder_rules(client, lib):
    # Not inside itself or its own subfolder.
    r = client.patch(
        f"{BASE}/folders/{lib['vorstand']}", json={"parentId": lib["finanzen"]}
    )
    assert r.status_code == 400
    # Unknown ids in the lists are dropped.
    r = client.patch(f"{BASE}/folders/{lib['allg']}", json={"roleIds": [99999]})
    assert r.get_json()["roleIds"] == [] and r.get_json()["restricted"] is False
    # Only empty folders go.
    r = client.delete(f"{BASE}/folders/{lib['vorstand']}")
    assert r.status_code == 409 and r.get_json()["error"] == "FOLDER_NOT_EMPTY"
    assert client.delete(f"{BASE}/folders/{lib['archiv']}").status_code == 204
    options = client.get(f"{BASE}/access-options").get_json()
    assert any(g["name"] == "Vorstand" for g in options["groups"])


def test_module_off_hides_the_api(client, auth_headers):
    set_modules(False, "documents")
    r = client.get(f"{BASE}/library")
    assert r.status_code == 403 and r.get_json()["error"] == "MODULE_DISABLED"


def test_the_plugin_loads_within_its_limits(app):
    from hubra.core.plugins import loader

    with app.app_context():
        spec = loader.current().get("documents")
    assert spec is not None and spec.loaded, spec and spec.error
    assert spec.manifest.get("uses") is not None
