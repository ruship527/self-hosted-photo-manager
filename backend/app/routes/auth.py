import os
import secrets

from fastapi import APIRouter, File, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse
from passlib.context import CryptContext

from app.utils import BASE_DIR

router = APIRouter(tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERNAME = "admin"
HASHED_PASSWORD = pwd_context.hash("1234")

active_sessions = {}


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
async def login(username: str = File(...), password: str = File(...)):
    if username != USERNAME:
        raise HTTPException(status_code=401, detail="Invalid username")

    if not pwd_context.verify(password, HASHED_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")

    session_token = secrets.token_urlsafe(32)
    active_sessions[session_token] = username

    response = RedirectResponse(url="/gallery", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True
    )

    return response


@router.get("/gallery")
def gallery(user: str = Depends(authenticate)):
    return FileResponse(os.path.join(BASE_DIR, "frontend", "index.html"))