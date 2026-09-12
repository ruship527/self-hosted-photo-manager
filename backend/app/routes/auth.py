import os
import secrets
import time

from fastapi import APIRouter, Form, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse
from passlib.context import CryptContext

from app.utils import BASE_DIR

router = APIRouter(tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERNAME = os.environ["ADMIN_USERNAME"]
HASHED_PASSWORD = os.environ["ADMIN_PASSWORD_HASH"]

SESSION_TTL_SECONDS = 3600

# Only mark the session cookie Secure (HTTPS-only) if explicitly enabled -
# e.g. once this sits behind a reverse proxy terminating TLS. On plain
# http:// (the default for a LAN-only homelab setup) Secure=True makes
# browsers silently discard the cookie, breaking login entirely.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "300"))

active_sessions: dict[str, dict] = {}
failed_login_attempts: dict[str, list] = {}

# Both dicts above only ever grow from login traffic and are only ever
# cleaned up lazily, for the one exact token/key being looked up right now
# - a session or IP that's never touched again just sits in memory forever
# on a long-running server. Sweep the rest out periodically, piggybacked on
# real login attempts rather than a background thread.
_SESSION_PRUNE_INTERVAL_SECONDS = 300
_last_session_prune = 0.0


def _prune_stale_auth_state():
    global _last_session_prune

    now = time.time()
    if now - _last_session_prune < _SESSION_PRUNE_INTERVAL_SECONDS:
        return
    _last_session_prune = now

    for token, session in list(active_sessions.items()):
        if session["expires"] < now:
            active_sessions.pop(token, None)

    for key, attempts in list(failed_login_attempts.items()):
        if not any(now - t < LOGIN_LOCKOUT_SECONDS for t in attempts):
            failed_login_attempts.pop(key, None)


def authenticate(request: Request):
    session_token = request.cookies.get("session_token")
    session = active_sessions.get(session_token) if session_token else None

    if not session or session["expires"] < time.time():
        active_sessions.pop(session_token, None)
        raise HTTPException(status_code=401, detail="Not logged in")

    return session["user"]


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(key: str):
    _prune_stale_auth_state()

    now = time.time()
    attempts = [t for t in failed_login_attempts.get(key, []) if now - t < LOGIN_LOCKOUT_SECONDS]
    failed_login_attempts[key] = attempts

    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        retry_after = int(LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after}s.",
        )


def _record_login_failure(key: str):
    failed_login_attempts.setdefault(key, []).append(time.time())


def _clear_login_failures(key: str):
    failed_login_attempts.pop(key, None)


@router.get("/")
def home():
    return RedirectResponse(url="/login")


@router.get("/login")
def login_page():
    return FileResponse(os.path.join(BASE_DIR, "frontend", "login.html"))


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    client_key = _client_key(request)
    _check_login_rate_limit(client_key)

    if username != USERNAME or not pwd_context.verify(password, HASHED_PASSWORD):
        _record_login_failure(client_key)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _clear_login_failures(client_key)

    session_token = secrets.token_urlsafe(32)
    active_sessions[session_token] = {
        "user": username,
        "expires": time.time() + SESSION_TTL_SECONDS,
    }

    response = RedirectResponse(url="/gallery", status_code=303)
    response.set_cookie(
        key="session_token", value=session_token,
        httponly=True, secure=COOKIE_SECURE, samesite="lax"
    )

    return response


@router.get("/gallery")
def gallery(user: str = Depends(authenticate)):
    return FileResponse(os.path.join(BASE_DIR, "frontend", "index.html"))

@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    active_sessions.pop(token, None)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response