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

active_sessions: dict[str, dict] = {}


def authenticate(request: Request):
    session_token = request.cookies.get("session_token")
    session = active_sessions.get(session_token) if session_token else None

    if not session or session["expires"] < time.time():
        active_sessions.pop(session_token, None)
        raise HTTPException(status_code=401, detail="Not logged in")

    return session["user"]


@router.get("/")
def home():
    return RedirectResponse(url="/login")


@router.get("/login")
def login_page():
    return FileResponse(os.path.join(BASE_DIR, "frontend", "login.html"))


@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if username != USERNAME or not pwd_context.verify(password, HASHED_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid username or password")

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