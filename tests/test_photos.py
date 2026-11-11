"""Photo albums: album folders, photos with thumbnails, tags, consent, and
the take-over of the Community plugin's albums."""

from __future__ import annotations

import io

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/documents"


def _png(colour=(200, 30, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(buf, "PNG")
    return buf.getvalue()


def _photos(client, album_id, *blobs):
    form = {"photos": [(io.BytesIO(b), f"p{i}.png", "image/png") for i, b in enumerate(blobs)]}
    return client.post(
        f"{BASE}/folders/{album_id}/photos", data=form, content_type="multipart/form-data"
    )


@pytest.fixture
def club(client, app, db, seeded_db, tmp_path):
    pytest.importorskip("PIL")
    set_modules(True, "documents")
    app.config["FILES_DIR"] = str(tmp_path)
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    max_ = _make_role_and_member(db, tier, name="Max", permission_keys=["documents.files.read"])
    lea = _make_role_and_member(db, tier, name="Lea", permission_keys=["documents.files.read"])
    return {"max": max_.id, "lea": lea.id}


def test_an_album_with_photos_tags_and_consent(client, db, club):
    _login(client, "admin@test.ch")
    album = client.post(
        f"{BASE}/folders", json={"kind": "album", "name": "Sommerfest", "takenOn": "2026-07-04"}
    ).get_json()
    assert (album["kind"], album["takenOn"], album["membersUpload"]) == (
        "album", "2026-07-04", True,
    )
    assert client.post(f"{BASE}/folders", json={"name": "x", "kind": "zoo"}).status_code == 400

    # Any reader adds photos to an album that lets members do so.
    _login(client, "max@test.ch")
    res = _photos(client, album["id"], _png(), b"not a photo")
    assert res.status_code == 201
    body = res.get_json()
    assert len(body["added"]) == 1 and len(body["failed"]) == 1
    photo = body["added"][0]
    assert photo["isPhoto"] and photo["width"] == 40
    assert client.get(f"{BASE}/files/{photo['id']}/thumb").status_code == 200
    assert client.patch(f"{BASE}/photos/{photo['id']}", json={"caption": "Grill"}).status_code == 200
    assert client.put(
        f"{BASE}/files/{photo['id']}/tags", json={"memberIds": [club["lea"]]}
    ).status_code == 204
    got = client.get(f"{BASE}/folders/{album['id']}").get_json()
    assert got["canUpload"] and got["files"][0]["caption"] == "Grill"
    assert [t["name"] for t in got["files"][0]["tags"]] == ["Test Lea"]
    listed = client.get(f"{BASE}/albums").get_json()["albums"]
    assert listed[0]["coverFileId"] == photo["id"] and listed[0]["fileCount"] == 1

    # Lea doesn't want photos of her: her tag goes and she can't be tagged.
    _login(client, "lea@test.ch")
    assert client.put(f"{BASE}/photo-consent", json={"allowed": False}).get_json() == {
        "photosOfMe": False
    }
    assert client.get(f"{BASE}/folders/{album['id']}").get_json()["files"][0]["tags"] == []
    assert client.patch(f"{BASE}/photos/{photo['id']}", json={"caption": "x"}).status_code == 403
    _login(client, "max@test.ch")
    assert client.put(
        f"{BASE}/files/{photo['id']}/tags", json={"memberIds": [club["lea"]]}
    ).status_code == 409

    # Closed for members: only writers add photos.
    _login(client, "admin@test.ch")
    client.patch(f"{BASE}/folders/{album['id']}", json={"membersUpload": False})
    _login(client, "max@test.ch")
    assert _photos(client, album["id"], _png()).status_code == 403
    assert client.delete(f"{BASE}/photos/{photo['id']}").status_code == 403

    # An album goes with its photos.
    _login(client, "admin@test.ch")
    assert client.delete(f"{BASE}/folders/{album['id']}").status_code == 204
    assert client.get(f"{BASE}/albums").get_json()["albums"] == []


def test_community_albums_move_in(client, app, db, club):
    from hubra.core.contracts import available

    from hubra_documents.models import DocumentFile, DocumentFolder, DocumentPhotoOptout
    from hubra_documents.takeover import take_over_albums

    set_modules(True, "community")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    if not available("community.albums.export"):
        pytest.skip("needs the Community plugin with the album export")
    _login(client, "admin@test.ch")
    community = "/api/v1/app/community"
    album = client.post(f"{community}/albums", json={"title": "GV 2026"}).get_json()
    form = {"photos": [(io.BytesIO(_png()), "a.png", "image/png")]}
    up = client.post(
        f"{community}/albums/{album['id']}/photos", data=form, content_type="multipart/form-data"
    ).get_json()
    photo_id = up["added"][0]["id"]
    client.patch(f"{community}/photos/{photo_id}", json={"caption": "Vorstand", "tags": [club["max"]]})
    _login(client, "lea@test.ch")
    client.put(f"{community}/consent", json={"allowed": False})

    assert take_over_albums() == {"albums": 1, "photos": 1}
    db.session.commit()
    assert take_over_albums() == {"albums": 0, "photos": 0}  # once only
    folder = db.session.query(DocumentFolder).filter_by(kind="album").one()
    assert folder.name == "GV 2026" and folder.source == f"community.album:{album['id']}"
    doc = db.session.query(DocumentFile).filter_by(folder_id=folder.id).one()
    assert doc.description == "Vorstand" and doc.file_key.split("/")[1] == "documents"
    assert db.session.query(DocumentPhotoOptout).filter_by(member_id=club["lea"]).count() == 1

    _login(client, "max@test.ch")
    got = client.get(f"{BASE}/folders/{folder.id}").get_json()
    assert [t["memberId"] for t in got["files"][0]["tags"]] == [club["max"]]
    assert client.get(f"{BASE}/files/{doc.id}/download?inline=1").status_code == 200


def _album(client):
    _login(client, "admin@test.ch")
    return client.post(f"{BASE}/folders", json={"kind": "album", "name": "Fest"}).get_json()


def test_a_huge_photo_is_refused_before_it_is_decoded(client, club):
    from PIL import Image

    from hubra_documents import images

    # A tiny PNG that claims more pixels than allowed.
    buf = io.BytesIO()
    Image.new("1", (8000, 8000)).save(buf, "PNG")
    assert 8000 * 8000 > images.MAX_PIXELS and len(buf.getvalue()) < 100_000
    with pytest.raises(images.BadImage):
        images.process(buf.getvalue())
    assert Image.MAX_IMAGE_PIXELS != images.MAX_PIXELS  # Pillow's global stays as it was


def test_a_photo_keeps_its_name_clean_and_its_thumb_an_image(client, club):
    album = _album(client)
    form = {"photos": [(io.BytesIO(_png()), "../a\tb.png", "image/png")]}
    res = client.post(
        f"{BASE}/folders/{album['id']}/photos", data=form, content_type="multipart/form-data"
    )
    photo = res.get_json()["added"][0]
    assert "\t" not in photo["name"] and "/" not in photo["name"]
    assert client.get(f"{BASE}/files/{photo['id']}/download").status_code == 200

    # A new version of a photo is a photo again: re-encoded, new thumbnail.
    form = {"file": (io.BytesIO(b"<script>alert(1)</script>"), "x.html", "text/html")}
    assert client.put(
        f"{BASE}/files/{photo['id']}/content", data=form, content_type="multipart/form-data"
    ).status_code == 400
    form = {"file": (io.BytesIO(_png((0, 0, 255))), "y.png", "text/html")}
    res = client.put(
        f"{BASE}/files/{photo['id']}/content", data=form, content_type="multipart/form-data"
    )
    assert res.status_code == 200 and res.get_json()["contentType"] == "image/jpeg"
    thumb = client.get(f"{BASE}/files/{photo['id']}/thumb")
    assert thumb.mimetype == "image/jpeg"
    assert "sandbox" in thumb.headers["Content-Security-Policy"]


def test_tags_take_member_ids_not_booleans(client, club):
    album = _album(client)
    photo = _photos(client, album["id"], _png()).get_json()["added"][0]
    assert client.put(
        f"{BASE}/files/{photo['id']}/tags", json={"memberIds": [True]}
    ).status_code == 400
