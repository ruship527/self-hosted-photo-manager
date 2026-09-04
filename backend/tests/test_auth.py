from conftest import TEST_USERNAME, TEST_PASSWORD


def test_home_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_login_wrong_password_is_rejected(client):
    resp = client.post("/login", data={"username": TEST_USERNAME, "password": "wrong"})
    assert resp.status_code == 401


def test_login_wrong_username_is_rejected(client):
    resp = client.post("/login", data={"username": "nobody", "password": TEST_PASSWORD})
    assert resp.status_code == 401


def test_login_success_sets_cookie_and_redirects(client):
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/gallery"
    assert "session_token" in resp.cookies


def test_gallery_requires_login(client):
    resp = client.get("/gallery")
    assert resp.status_code == 401


def test_gallery_accessible_after_login(logged_in_client):
    resp = logged_in_client.get("/gallery")
    assert resp.status_code == 200


def test_logout_clears_session(logged_in_client):
    resp = logged_in_client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303

    resp = logged_in_client.get("/gallery")
    assert resp.status_code == 401


def test_login_rate_limit_locks_out_after_repeated_failures(client):
    for _ in range(5):
        resp = client.post("/login", data={"username": TEST_USERNAME, "password": "wrong"})
        assert resp.status_code == 401

    resp = client.post("/login", data={"username": TEST_USERNAME, "password": "wrong"})
    assert resp.status_code == 429

    # Even the correct password is locked out until the window expires
    resp = client.post("/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    assert resp.status_code == 429


def test_api_routes_require_login(client):
    for method, path in [
        ("get", "/photos"),
        ("get", "/files"),
        ("get", "/stats"),
        ("get", "/albums/data"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, f"{method.upper()} {path} should require auth"
