from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
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

    safe_name = sanitize_filename(file.filename)
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

    taken_date = get_photo_taken_date(temp_path)
    new_filename = build_filename(file.filename)
    new_path = os.path.join(PHOTO_FOLDER, new_filename)

    os.rename(temp_path, new_path)

    #AI TAGGING
    tags_str = generate_ai_tags(new_path)

    # Save to DB
    photo = Photo(
        original_filename=file.filename,
        saved_filename=new_filename,
        taken_date=taken_date,
        upload_date=datetime.now().isoformat(),
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
            "taken_date": p.taken_date,
            "upload_date": p.upload_date,
            "tags": p.tags.split(",") if (show_tags and p.tags) else [],
            "album": p.album or "Unsorted",

        }
        for p in photos
    ]

@router.post("/photos/download-zip")
async def download_zip(filenames: list[str], user: str = Depends(authenticate)):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for name in filenames:
            try:
                file_path = safe_join(PHOTO_FOLDER, name)
            except ValueError:
                continue

            if os.path.isfile(file_path):
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
    except ValueError:
        file_path = None

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

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
            "taken_date": p.taken_date,
            "upload_date": p.upload_date,
            "album": p.album or "Unsorted",
        }
        for p in photos
    ]
