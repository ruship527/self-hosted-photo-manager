import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database import engine, Base
import app.models

from app.routes import auth, photos, files, stats, albums
from app.routes.auth import authenticate
from app.utils import (
    UPLOAD_FOLDER,
    PHOTO_FOLDER,
    THUMBNAIL_FOLDER,
    is_safe_to_render_inline,
    make_thumbnail,
    safe_join,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("photoapp")

app = FastAPI()

# Convenient for a fresh dev/test DB (create_all only ever adds *missing*
# tables, so it's a no-op once they exist) but it's not a substitute for
# Alembic - it will never apply a change to an existing column. Schema
# changes from here on go through an Alembic migration in alembic/versions/
# ("alembic upgrade head"). An existing database that already has these
# tables (every deploy up to this point) should run "alembic stamp head"
# once instead, to mark the baseline as already applied without re-running
# its DDL.
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


@app.middleware("http")
async def add_nosniff_header(request: Request, call_next):
    """Defense-in-depth alongside is_safe_to_render_inline(): even if a
    served file's content-type is ever wrong (a future bug, or a client
    that mis-detects/sniffs regardless), this stops a browser from
    reinterpreting a declared type into something more dangerous."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/uploads/thumbnails/{filename}")
def get_thumbnail(filename: str, user: str = Depends(authenticate)):
    try:
        original_path = safe_join(PHOTO_FOLDER, filename)
        thumb_path = safe_join(THUMBNAIL_FOLDER, filename)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")

    if not os.path.isfile(original_path):
        raise HTTPException(status_code=404, detail="Not found")

    if not os.path.isfile(thumb_path):
        try:
            make_thumbnail(original_path, thumb_path)
        except Exception:
            logger.exception("Thumbnail generation failed for %s", filename)
            return FileResponse(original_path)  # better a slow image than a broken one

    return FileResponse(thumb_path)


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

    # The "files" upload has no content-type check, so anything could be
    # sitting in FILE_FOLDER - only extensions known not to execute as
    # active content when rendered inline are served as-is; everything
    # else (including an unrecognized or missing extension) downloads
    # instead of rendering in this app's own (authenticated) origin.
    if subfolder == "files" and not is_safe_to_render_inline(file_path):
        return FileResponse(
            file_path,
            media_type="application/octet-stream",
            filename=os.path.basename(file_path),
        )

    return FileResponse(file_path)


app.include_router(auth.router)
app.include_router(photos.router)
app.include_router(files.router)
app.include_router(stats.router)
app.include_router(albums.router)