import io

from PIL import Image


def _make_test_image_bytes(color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=color).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_photo_upload_list_and_delete_roundtrip(logged_in_client, monkeypatch):
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    resp = logged_in_client.post(
        "/photos/upload",
        files={"file": ("test.png", _make_test_image_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"].endswith(".png")
    assert body["thumbnail_url"] == f"/uploads/thumbnails/{body['filename']}"

    resp = logged_in_client.get("/photos")
    assert resp.status_code == 200
    filenames = [p["filename"] for p in resp.json()]
    assert body["filename"] in filenames

    resp = logged_in_client.delete(f"/photos/{body['filename']}")
    assert resp.status_code == 200

    resp = logged_in_client.get("/photos")
    filenames = [p["filename"] for p in resp.json()]
    assert body["filename"] not in filenames


def test_thumbnail_is_generated_and_smaller_than_original(logged_in_client, monkeypatch):
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    buf = io.BytesIO()
    Image.new("RGB", (1000, 1000), color=(10, 20, 30)).save(buf, format="PNG")
    buf.seek(0)

    resp = logged_in_client.post(
        "/photos/upload",
        files={"file": ("big.png", buf, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()

    original = logged_in_client.get(body["url"])
    thumb = logged_in_client.get(body["thumbnail_url"])

    assert original.status_code == 200
    assert thumb.status_code == 200
    assert len(thumb.content) < len(original.content)

    thumb_img = Image.open(io.BytesIO(thumb.content))
    assert max(thumb_img.size) <= 400


def test_thumbnail_requires_login(logged_in_client, monkeypatch):
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    resp = logged_in_client.post(
        "/photos/upload",
        files={"file": ("auth-check.png", _make_test_image_bytes(color=(7, 7, 7)), "image/png")},
    )
    filename = resp.json()["filename"]

    # logged_in_client and the `client` fixture resolve to the same cached
    # instance within one test, so simulate logging out by dropping cookies
    # rather than requesting a second "fresh" client fixture.
    logged_in_client.cookies.clear()
    resp = logged_in_client.get(f"/uploads/thumbnails/{filename}")
    assert resp.status_code == 401


def test_photo_upload_rejects_non_image_content(logged_in_client, monkeypatch):
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    fake_image = io.BytesIO(b"not actually a png")
    resp = logged_in_client.post(
        "/photos/upload",
        files={"file": ("fake.png", fake_image, "image/png")},
    )
    assert resp.status_code == 400


def test_photos_pagination_is_opt_in(logged_in_client, monkeypatch):
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    for i in range(3):
        logged_in_client.post(
            "/photos/upload",
            files={"file": (f"test{i}.png", _make_test_image_bytes(color=(i, i, i)), "image/png")},
        )

    resp = logged_in_client.get("/photos")
    assert len(resp.json()) >= 3

    resp = logged_in_client.get("/photos", params={"limit": 1})
    assert len(resp.json()) == 1


def test_download_zip_rejects_an_oversized_batch(logged_in_client):
    import app.routes.photos as photos_module

    filenames = [f"photo{i}.jpg" for i in range(photos_module.MAX_ZIP_BATCH + 1)]
    resp = logged_in_client.post("/photos/download-zip", json=filenames)
    assert resp.status_code == 413


def test_download_zip_allows_a_batch_at_the_limit(logged_in_client):
    import app.routes.photos as photos_module

    filenames = [f"photo{i}.jpg" for i in range(photos_module.MAX_ZIP_BATCH)]
    resp = logged_in_client.post("/photos/download-zip", json=filenames)
    assert resp.status_code == 200
