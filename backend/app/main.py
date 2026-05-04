from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base
import app.models

from app.routes import auth, photos, files, stats, albums
from app.utils import UPLOAD_FOLDER

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")

app.include_router(auth.router)
app.include_router(photos.router)
app.include_router(files.router)
app.include_router(stats.router)
app.include_router(albums.router)