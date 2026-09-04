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

    resp = logged_in_client.get("/photos")
    assert resp.status_code == 200
    filenames = [p["filename"] for p in resp.json()]
    assert body["filename"] in filenames

    resp = logged_in_client.delete(f"/photos/{body['filename']}")
    assert resp.status_code == 200

    resp = logged_in_client.get("/photos")
    filenames = [p["filename"] for p in resp.json()]
    assert body["filename"] not in filenames


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
