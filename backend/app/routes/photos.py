from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Photo
import os
import zipfile
import io
from datetime import datetime
from pydantic import BaseModel
import uuid

from app.routes.auth import authenticate

router = APIRouter()

class AlbumUpdate(BaseModel):
    album: str

from app.utils import (
    PHOTO_FOLDER,
    FILE_FOLDER,
    THUMBNAIL_FOLDER,
    MAX_UPLOAD_MB,
    MAX_UPLOAD_BYTES,
    get_file_hash,
    get_photo_taken_date,
    build_filename,
    generate_ai_tags,
    sanitize_filename,
    safe_join,
    save_upload,
    is_valid_image,
    make_thumbnail,
    logger,
)



@router.post("/photos/upload")
async def upload_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    if file.content_type and file.content_type.startswith("image/"):
        folder = PHOTO_FOLDER
    else:
        folder = FILE_FOLDER

    try:
        safe_name = sanitize_filename(file.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    temp_filename = f"temp_{uuid.uuid4()}_{safe_name}"
    temp_path = os.path.join(folder, temp_filename)

    try:
        save_upload(file, temp_path, MAX_UPLOAD_BYTES)
    except ValueError:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_MB}MB upload limit")

    # Handle non-image files
    if folder == FILE_FOLDER:
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "url": f"/uploads/files/{file.filename}",
        }

    # The client-supplied content-type is easy to spoof - confirm the bytes
    # we actually saved decode as a real image before treating it as one.
    if not is_valid_image(temp_path):
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail="File is not a valid image")

    file_hash = get_file_hash(temp_path)

    # Check duplicate
    existing = db.query(Photo).filter(Photo.file_hash == file_hash).first()
    if existing:
        os.remove(temp_path)
        return {
            "message": "Duplicate image",
            "filename": existing.saved_filename,
        }

    # Captured once, up front - get_photo_taken_date's fallback (used when
    # there's no EXIF date) and the upload_date field below must be the
    # exact same instant. Computing them as two separate datetime.now()
    # calls straddling the slow AI-tagging step let them drift by however
    # long tagging took, so a photo with no EXIF looked "taken" seconds
    # before it was actually uploaded.
    upload_time = datetime.now()
    taken_date = get_photo_taken_date(temp_path, fallback=upload_time.strftime("%Y-%m-%d %H:%M:%S"))
    new_filename = build_filename(file.filename)
    new_path = os.path.join(PHOTO_FOLDER, new_filename)

    os.rename(temp_path, new_path)

    try:
        make_thumbnail(new_path, os.path.join(THUMBNAIL_FOLDER, new_filename))
    except Exception:
        logger.exception("Thumbnail generation failed for %s", new_filename)
        # not fatal - it'll be generated on first view instead

    # AI TAGGING - generate_ai_tags runs a BLIP model on CPU (~1.5-10s,
    # more on first call while the model loads). It's a synchronous, CPU-
    # bound call, so running it inline here blocked the whole async event
    # loop for that long on every single upload - not just this request,
    # every other page/API call on the server stalled too. run_in_threadpool
    # moves it off the event loop so the rest of the app stays responsive
    # while it runs.
    tags_str = await run_in_threadpool(generate_ai_tags, new_path)

    # Save to DB
    photo = Photo(
        original_filename=file.filename,
        saved_filename=new_filename,
        taken_date=taken_date,
        upload_date=upload_time.isoformat(),
        file_hash=file_hash,
        tags=tags_str,
        album="Unsorted"
    )

    db.add(photo)
    db.commit()
    db.refresh(photo)

    return {
        "id": photo.id,
        "filename": new_filename,
        "taken_date": taken_date,
        "tags": tags_str.split(","),
        "url": f"/uploads/photos/{new_filename}",
        "thumbnail_url": f"/uploads/thumbnails/{new_filename}",
    }

@router.get("/photos")
def get_photos(
    search: str = "",
    date: str = "",
    show_tags: bool = False,
    limit: int | None = None,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    query = db.query(Photo)

    if search:
        query = query.filter(
            Photo.saved_filename.contains(search)
            | Photo.taken_date.contains(search)
            | Photo.tags.contains(search)
        )

    if date:
        exif_date = date.replace("-", ":")
        query = query.filter(Photo.taken_date.contains(exif_date))

    query = query.order_by(Photo.id.desc())

    # Pagination is opt-in: with no limit given, behavior is unchanged
    # (returns everything) so the existing frontend keeps working as-is.
    if offset:
        query = query.offset(offset)

    if limit:
        query = query.limit(min(limit, 500))

    photos = query.all()

    return [
        {
            "id": p.id,
            "filename": p.saved_filename,
            "url": f"/uploads/photos/{p.saved_filename}",
            "thumbnail_url": f"/uploads/thumbnails/{p.saved_filename}",
            "taken_date": p.taken_date,
            "upload_date": p.upload_date,
            "tags": p.tags.split(",") if (show_tags and p.tags) else [],
            "album": p.album or "Unsorted",

        }
        for p in photos
    ]

MAX_ZIP_BATCH = 500

# Capping the number of files isn't enough on its own - the zip is still
# built entirely in memory, so e.g. 500 files (the count limit) at
# MAX_UPLOAD_MB each could still ask for ~250GB of RAM. Resolve every path
# and total up real file sizes *before* writing anything into the buffer,
# so an oversized request is rejected up front instead of partway through.
MAX_ZIP_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


@router.post("/photos/download-zip")
async def download_zip(filenames: list[str], user: str = Depends(authenticate)):
    if len(filenames) > MAX_ZIP_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files requested at once (max {MAX_ZIP_BATCH})",
        )

    file_paths = []
    total_bytes = 0

    for name in filenames:
        try:
            file_path = safe_join(PHOTO_FOLDER, name)
        except ValueError:
            continue

        if os.path.isfile(file_path):
            total_bytes += os.path.getsize(file_path)
            file_paths.append(file_path)

    if total_bytes > MAX_ZIP_TOTAL_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Requested files are too large to zip at once (max {MAX_ZIP_TOTAL_BYTES} bytes)",
        )

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for file_path in file_paths:
            zip_file.write(file_path, arcname=os.path.basename(file_path))

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=photos.zip"}
    )




@router.delete("/photos/{filename}")
def delete_photo(filename: str, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    photo = db.query(Photo).filter(Photo.saved_filename == filename).first()

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found in database")

    try:
        file_path = safe_join(PHOTO_FOLDER, filename)
        thumb_path = safe_join(THUMBNAIL_FOLDER, filename)
    except ValueError:
        file_path = None
        thumb_path = None

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    if thumb_path and os.path.exists(thumb_path):
        os.remove(thumb_path)

    db.delete(photo)
    db.commit()

    return {
        "message": "Photo deleted successfully",
        "filename": filename,
    }

@router.post("/photos/{filename}/album")
def update_photo_album(
    filename: str,
    data: AlbumUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate),
):
    photo = db.query(Photo).filter(Photo.saved_filename == filename).first()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.album = data.album
    db.commit()

    return {
        "message": "Album updated",
        "filename": filename,
        "album": data.album
    }





@router.get("/photos/album/{album}")
def get_photos_by_album(album: str, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    photos = db.query(Photo).filter(Photo.album == album).order_by(Photo.id.desc()).all()

    return [
        {
            "id": p.id,
            "filename": p.saved_filename,
            "url": f"/uploads/photos/{p.saved_filename}",
            "thumbnail_url": f"/uploads/thumbnails/{p.saved_filename}",
            "taken_date": p.taken_date,
            "upload_date": p.upload_date,
            "album": p.album or "Unsorted",
        }
        for p in photos
    ]
