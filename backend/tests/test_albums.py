import uuid

from conftest import upload_test_photo
from app.models import AlbumPhoto


def _unique_name(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_album(client, name):
    resp = client.post("/albums/create", data={"name": name}, follow_redirects=False)
    assert resp.status_code == 303

    albums = client.get("/albums/data").json()
    matches = [a for a in albums if a["name"] == name]
    assert matches, f"album {name!r} was not created"
    return matches[-1]["id"]


def test_create_album_requires_login(client):
    resp = client.post("/albums/create", data={"name": "nope"}, follow_redirects=False)
    assert resp.status_code == 401


def test_create_album_appears_in_albums_data(logged_in_client):
    name = _unique_name("Vacation")
    album_id = _create_album(logged_in_client, name)

    albums = logged_in_client.get("/albums/data").json()
    assert any(a["id"] == album_id and a["name"] == name for a in albums)


def test_create_album_rejects_blank_name(logged_in_client):
    resp = logged_in_client.post(
        "/albums/create", data={"name": "   "}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/albums?error=Album+name+can%27t+be+empty"


def test_create_album_rejects_case_insensitive_duplicate(logged_in_client):
    name = _unique_name("Trip")
    _create_album(logged_in_client, name)

    resp = logged_in_client.post(
        "/albums/create", data={"name": name.upper()}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/albums?error=")

    albums = logged_in_client.get("/albums/data").json()
    matching = [a for a in albums if a["name"].lower() == name.lower()]
    assert len(matching) == 1


def test_rename_album_updates_name(logged_in_client):
    album_id = _create_album(logged_in_client, _unique_name("Old"))
    new_name = _unique_name("New")

    resp = logged_in_client.post(
        f"/albums/{album_id}/rename", data={"name": new_name}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/albums/{album_id}"

    albums = logged_in_client.get("/albums/data").json()
    assert any(a["id"] == album_id and a["name"] == new_name for a in albums)


def test_rename_album_rejects_blank_name(logged_in_client):
    album_id = _create_album(logged_in_client, _unique_name("Keep"))

    resp = logged_in_client.post(
        f"/albums/{album_id}/rename", data={"name": " "}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/albums/{album_id}?error=Album+name+can%27t+be+empty"


def test_rename_album_rejects_duplicate_of_another_album(logged_in_client):
    taken_name = _unique_name("Taken")
    _create_album(logged_in_client, taken_name)
    album_id = _create_album(logged_in_client, _unique_name("Renamable"))

    resp = logged_in_client.post(
        f"/albums/{album_id}/rename", data={"name": taken_name}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith(f"/albums/{album_id}?error=")

    albums = logged_in_client.get("/albums/data").json()
    renamed = next(a for a in albums if a["id"] == album_id)
    assert renamed["name"] != taken_name


def test_rename_album_allows_keeping_its_own_name(logged_in_client):
    name = _unique_name("SameName")
    album_id = _create_album(logged_in_client, name)

    resp = logged_in_client.post(
        f"/albums/{album_id}/rename", data={"name": name}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/albums/{album_id}"


def test_rename_nonexistent_album_returns_404(logged_in_client):
    resp = logged_in_client.post("/albums/999999/rename", data={"name": "whatever"})
    assert resp.status_code == 404


def test_get_nonexistent_album_returns_404(logged_in_client):
    resp = logged_in_client.get("/albums/999999")
    assert resp.status_code == 404


def test_add_photo_to_album_appears_in_detail_page(logged_in_client, monkeypatch):
    album_id = _create_album(logged_in_client, _unique_name("Photos"))
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="in-album.png")

    resp = logged_in_client.post(
        f"/albums/{album_id}/add/{photo['id']}", follow_redirects=False
    )
    assert resp.status_code == 303

    detail = logged_in_client.get(f"/albums/{album_id}")
    assert detail.status_code == 200
    assert photo["filename"] in detail.text


def test_add_photo_to_album_is_idempotent(logged_in_client, monkeypatch, db_session):
    album_id = _create_album(logged_in_client, _unique_name("Dedup"))
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="dup.png")

    for _ in range(2):
        resp = logged_in_client.post(
            f"/albums/{album_id}/add/{photo['id']}", follow_redirects=False
        )
        assert resp.status_code == 303

    rows = (
        db_session.query(AlbumPhoto)
        .filter(AlbumPhoto.album_id == album_id, AlbumPhoto.photo_id == photo["id"])
        .all()
    )
    assert len(rows) == 1


def test_add_photo_to_nonexistent_album_returns_404(logged_in_client, monkeypatch):
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="orphan.png")
    resp = logged_in_client.post(f"/albums/999999/add/{photo['id']}")
    assert resp.status_code == 404


def test_add_nonexistent_photo_to_album_returns_404(logged_in_client):
    album_id = _create_album(logged_in_client, _unique_name("Empty"))
    resp = logged_in_client.post(f"/albums/{album_id}/add/999999")
    assert resp.status_code == 404


def test_bulk_add_photos_to_album(logged_in_client, monkeypatch, db_session):
    album_id = _create_album(logged_in_client, _unique_name("Batch"))
    photo1 = upload_test_photo(logged_in_client, monkeypatch, filename="b1.png", color=(1, 1, 1))
    photo2 = upload_test_photo(logged_in_client, monkeypatch, filename="b2.png", color=(2, 2, 2))

    resp = logged_in_client.post(
        f"/albums/{album_id}/add-photos",
        data={"photo_ids": [photo1["id"], photo2["id"]]},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    linked_ids = {
        row.photo_id
        for row in db_session.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id)
    }
    assert linked_ids == {photo1["id"], photo2["id"]}

    # Re-submitting the same batch shouldn't create duplicate rows.
    resp = logged_in_client.post(
        f"/albums/{album_id}/add-photos",
        data={"photo_ids": [photo1["id"], photo2["id"]]},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    rows = db_session.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).all()
    assert len(rows) == 2


def test_bulk_add_photos_ignores_unknown_photo_ids(logged_in_client, db_session):
    album_id = _create_album(logged_in_client, _unique_name("Ignore"))

    resp = logged_in_client.post(
        f"/albums/{album_id}/add-photos",
        data={"photo_ids": [999999]},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    rows = db_session.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).all()
    assert rows == []


def test_remove_photo_from_album(logged_in_client, monkeypatch, db_session):
    album_id = _create_album(logged_in_client, _unique_name("Removable"))
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="removeme.png")
    logged_in_client.post(f"/albums/{album_id}/add/{photo['id']}")

    resp = logged_in_client.delete(f"/albums/{album_id}/remove/{photo['id']}")
    assert resp.status_code == 200

    remaining = (
        db_session.query(AlbumPhoto)
        .filter(AlbumPhoto.album_id == album_id, AlbumPhoto.photo_id == photo["id"])
        .first()
    )
    assert remaining is None


def test_remove_photo_not_in_album_returns_404(logged_in_client, monkeypatch):
    album_id = _create_album(logged_in_client, _unique_name("NeverAdded"))
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="never-added.png")

    resp = logged_in_client.delete(f"/albums/{album_id}/remove/{photo['id']}")
    assert resp.status_code == 404


def test_delete_album_removes_it_and_its_photo_links(logged_in_client, monkeypatch, db_session):
    album_id = _create_album(logged_in_client, _unique_name("Doomed"))
    photo = upload_test_photo(logged_in_client, monkeypatch, filename="doomed.png")
    logged_in_client.post(f"/albums/{album_id}/add/{photo['id']}")

    resp = logged_in_client.post(f"/albums/{album_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/albums"

    albums = logged_in_client.get("/albums/data").json()
    assert all(a["id"] != album_id for a in albums)

    remaining_links = (
        db_session.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).all()
    )
    assert remaining_links == []


def test_delete_nonexistent_album_returns_404(logged_in_client):
    resp = logged_in_client.post("/albums/999999/delete")
    assert resp.status_code == 404
