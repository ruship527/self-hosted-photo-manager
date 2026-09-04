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
