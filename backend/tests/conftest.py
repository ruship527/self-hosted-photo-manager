import io
import itertools
import os
import shutil
import tempfile

# All env vars that config modules read at import time must be set BEFORE
# anything under `app` gets imported below.
_TEST_ROOT = tempfile.mkdtemp(prefix="photoapp-test-")

os.environ.setdefault("DATA_DIR", os.path.join(_TEST_ROOT, "data"))
os.environ.setdefault("UPLOAD_FOLDER", os.path.join(_TEST_ROOT, "uploads"))
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ALLOWED_ORIGINS", "")

TEST_USERNAME = "testadmin"
TEST_PASSWORD = "correct horse battery staple"

if "ADMIN_USERNAME" not in os.environ or "ADMIN_PASSWORD_HASH" not in os.environ:
    from passlib.context import CryptContext

    os.environ["ADMIN_USERNAME"] = TEST_USERNAME
    os.environ["ADMIN_PASSWORD_HASH"] = CryptContext(schemes=["bcrypt"]).hash(TEST_PASSWORD)

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.database import SessionLocal
from app.main import app
from app.routes import auth as auth_module


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_auth_state():
    """Sessions and rate-limit counters are module-level in-memory dicts,
    so tests need a clean slate each time."""
    auth_module.active_sessions.clear()
    auth_module.failed_login_attempts.clear()
    yield
    auth_module.active_sessions.clear()
    auth_module.failed_login_attempts.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def logged_in_client(client):
    resp = client.post(
        "/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "session_token" in resp.cookies
    return client


@pytest.fixture
def db_session():
    """Direct DB access for assertions the JSON/HTML endpoints don't expose
    (e.g. that an AlbumPhoto row was actually removed, not just hidden)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Uploads are deduped by file content hash, not filename - two calls with
# the same pixel color produce the same image bytes and the second is
# treated as a re-upload of the first. Each call gets its own color by
# default so tests can't collide with each other over a whole run.
_test_image_colors = itertools.cycle(
    (r, g, b)
    for r in (10, 90, 170, 250)
    for g in (30, 110, 190)
    for b in (50, 130, 210)
)


def make_test_image_bytes(color=None, size=(4, 4)):
    if color is None:
        color = next(_test_image_colors)

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    buf.seek(0)
    return buf


def upload_test_photo(client, monkeypatch, filename="test.png", color=None):
    """Upload a small in-memory PNG through the real upload endpoint and
    return the parsed JSON response. AI tagging is stubbed out so tests
    don't have to load the BLIP model."""
    import app.routes.photos as photos_module
    monkeypatch.setattr(photos_module, "generate_ai_tags", lambda path: "")

    resp = client.post(
        "/photos/upload",
        files={"file": (filename, make_test_image_bytes(color), "image/png")},
    )
    assert resp.status_code == 200
    return resp.json()
