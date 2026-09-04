import os
import secrets
from time import time

from fastapi import APIRouter, File, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse
from passlib.context import CryptContext

from app.utils import BASE_DIR

router = APIRouter(tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERNAME = os.environ["ADMIN_USERNAME"]
HASHED_PASSWORD = os.environ["ADMIN_PASSWORD_HASH"] 

active_sessions[session_token] = {"user": username, "expires": time.time() + 3600}

def authenticate(request: Request):
    session_token = request.cookies.get("session_token")

    if not session_token or session_token not in active_sessions:
        raise HTTPException(status_code=401, detail="Not logged in")

    return active_sessions[session_token]


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
    active_sessions[session_token] = username

    response = RedirectResponse(url="/gallery", status_code=303)
    response.set_cookie(
    key="session_token", value=session_token,
    httponly=True, secure=True, samesite="lax"
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