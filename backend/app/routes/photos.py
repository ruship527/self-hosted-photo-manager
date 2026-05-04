from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from app.database import SessionLocal
from app.models import Photo
import os
import shutil
import zipfile
import io
from datetime import datetime
from pydantic import BaseModel
import uuid
from fastapi.templating import Jinja2Templates



router = APIRouter()
templates = Jinja2Templates(directory="/home/rushi/Photoapp/frontend/")

class AlbumUpdate(BaseModel):
    album: str

from app.utils import (
    PHOTO_FOLDER,
    FILE_FOLDER,
    get_file_hash,
    get_photo_taken_date,
    build_filename,
    generate_ai_tags
)



@router.post("/photos/upload")
async def upload_photo(file: UploadFile = File(...)):
    db = SessionLocal()

    if file.content_type and file.content_type.startswith("image/"):
        folder = PHOTO_FOLDER
    else:
        folder = FILE_FOLDER

    temp_filename = f"temp_{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(folder, temp_filename)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_hash = get_file_hash(temp_path)

    # Handle non-image files
    if folder == FILE_FOLDER:
        db.close()
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "url": f"/uploads/files/{file.filename}",
        }

    # Check duplicate
    existing = db.query(Photo).filter(Photo.file_hash == file_hash).first()
    if existing:
        os.remove(temp_path)
        db.close()
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
    db.close()

    return {
        "id": photo.id,
        "filename": new_filename,
        "taken_date": taken_date,
        "tags": tags_str.split(","), 
        "url": f"/uploads/photos/{new_filename}",
    }

@router.get("/photos")
def get_photos(search: str = "", date: str = "", show_tags: bool = False):
    db = SessionLocal()

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

    photos = query.order_by(Photo.id.desc()).all()
    db.close()

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

@router.get("/gallery", response_class=HTMLResponse)
def gallery_page():
    return FileResponse("/home/rushi/Photoapp/frontend/photos.html")

@router.post("/photos/download-zip")
async def download_zip(filenames: list[str]):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for name in filenames:
            file_path = os.path.join(PHOTO_FOLDER, name)

            if os.path.exists(file_path):
                zip_file.write(file_path, arcname=name)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=photos.zip"}
    )




@router.delete("/photos/{filename}")
def delete_photo(filename: str):
    db = SessionLocal()

    photo = db.query(Photo).filter(Photo.saved_filename == filename).first()

    if photo is None:
        db.close()
        raise HTTPException(status_code=404, detail="Photo not found in database")

    file_path = os.path.join(PHOTO_FOLDER, filename)

    if os.path.exists(file_path):
        os.remove(file_path)

    db.delete(photo)
    db.commit()
    db.close()

    return {
        "message": "Photo deleted successfully",
        "filename": filename,
    }

@router.post("/photos/{filename}/album")
def update_photo_album(filename: str, data: AlbumUpdate):
    db = SessionLocal()

    photo = db.query(Photo).filter(Photo.saved_filename == filename).first()

    if not photo:
        db.close()
        raise HTTPException(status_code=404, detail="Photo not found")

    photo.album = data.album
    db.commit()
    db.close()

    return {
        "message": "Album updated",
        "filename": filename,
        "album": data.album
    }





@router.get("/photos/album/{album}")
def get_photos_by_album(album: str):
    db = SessionLocal()

    photos = db.query(Photo).filter(Photo.album == album).order_by(Photo.id.desc()).all()
    db.close()

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