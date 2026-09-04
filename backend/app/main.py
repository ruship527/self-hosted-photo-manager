import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database import engine, Base
import app.models

from app.routes import auth, photos, files, stats, albums
from app.routes.auth import authenticate
from app.utils import UPLOAD_FOLDER, safe_join

app = FastAPI()

Base.metadata.create_all(bind=engine)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/uploads/{subfolder}/{filename}")
def get_upload(subfolder: str, filename: str, user: str = Depends(authenticate)):
    if subfolder not in {"photos", "files"}:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        file_path = safe_join(os.path.join(UPLOAD_FOLDER, subfolder), filename)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(file_path)


app.include_router(auth.router)
app.include_router(photos.router)
app.include_router(files.router)
app.include_router(stats.router)
app.include_router(albums.router)