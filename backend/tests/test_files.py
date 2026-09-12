def _upload_file(client, filename, content=b"hello world", content_type="application/octet-stream"):
    resp = client.post(
        "/files/upload",
        files={"file": (filename, content, content_type)},
    )
    assert resp.status_code == 200
    return resp.json()["filename"]


def test_upload_list_and_delete_roundtrip(logged_in_client):
    saved_name = _upload_file(logged_in_client, "notes.txt", content=b"just some notes")

    files = logged_in_client.get("/files").json()
    assert any(f["filename"] == saved_name for f in files)

    resp = logged_in_client.delete(f"/files/{saved_name}")
    assert resp.status_code == 200

    files = logged_in_client.get("/files").json()
    assert all(f["filename"] != saved_name for f in files)


def test_uploaded_files_require_login(logged_in_client):
    saved_name = _upload_file(logged_in_client, "private.txt")

    logged_in_client.cookies.clear()
    resp = logged_in_client.get(f"/uploads/files/{saved_name}")
    assert resp.status_code == 401


def test_ordinary_file_serves_with_its_own_content_type(logged_in_client):
    saved_name = _upload_file(logged_in_client, "notes.txt", content=b"just some notes", content_type="text/plain")

    resp = logged_in_client.get(f"/uploads/files/{saved_name}")
    assert resp.status_code == 200
    assert "attachment" not in resp.headers.get("content-disposition", "")


def test_uploaded_html_is_forced_to_download_not_rendered(logged_in_client):
    """The generic file upload has no content-type check, so nothing stops
    someone uploading an .html file. If it were served back with its
    natural text/html content-type, a browser opening it would execute
    that HTML/JS as if it were part of this app's own origin - so it must
    come back as a forced download instead."""
    payload = b"<script>alert(document.cookie)</script>"
    saved_name = _upload_file(logged_in_client, "page.html", content=payload, content_type="text/html")

    resp = logged_in_client.get(f"/uploads/files/{saved_name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content == payload


def test_uploaded_svg_is_forced_to_download_not_rendered(logged_in_client):
    payload = b"<svg onload=\"alert(1)\"></svg>"
    saved_name = _upload_file(logged_in_client, "icon.svg", content=payload, content_type="image/svg+xml")

    resp = logged_in_client.get(f"/uploads/files/{saved_name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in resp.headers["content-disposition"]


def test_uploaded_file_with_an_unrecognized_extension_is_forced_to_download():
    """is_safe_to_render_inline() is deliberately an allowlist, not a
    denylist - an extension nobody thought to allow (not just ones known
    to be dangerous) must still default to downloading, not rendering."""
    from app.utils import is_safe_to_render_inline
    assert is_safe_to_render_inline("mystery.xht") is False
    assert is_safe_to_render_inline("mystery.svgz") is False


def test_uploaded_file_with_no_extension_is_forced_to_download(logged_in_client):
    payload = b"<script>alert(document.cookie)</script>"
    saved_name = _upload_file(logged_in_client, "mystery", content=payload, content_type="application/octet-stream")

    resp = logged_in_client.get(f"/uploads/files/{saved_name}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in resp.headers["content-disposition"]


def test_responses_carry_nosniff_header(logged_in_client):
    resp = logged_in_client.get("/files")
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_upload_avoids_clobbering_a_same_named_file(logged_in_client):
    name1 = _upload_file(logged_in_client, "dup.txt", content=b"first")
    name2 = _upload_file(logged_in_client, "dup.txt", content=b"second")

    assert name1 != name2

    resp1 = logged_in_client.get(f"/uploads/files/{name1}")
    resp2 = logged_in_client.get(f"/uploads/files/{name2}")
    assert resp1.content == b"first"
    assert resp2.content == b"second"


def test_delete_nonexistent_file_returns_404(logged_in_client):
    resp = logged_in_client.delete("/files/does-not-exist.txt")
    assert resp.status_code == 404


def test_delete_file_rejects_path_traversal(logged_in_client):
    resp = logged_in_client.delete("/files/..%2F..%2Fapp%2Fmain.py")
    assert resp.status_code == 404
