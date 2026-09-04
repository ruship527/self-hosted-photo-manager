import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Photo
from app.routes.auth import authenticate
from app.utils import PHOTO_FOLDER, FILE_FOLDER

router = APIRouter(tags=["Stats"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    photos = db.query(Photo).all()

    total_photos = len(photos)
    os.makedirs(FILE_FOLDER, exist_ok=True)
    files = os.listdir(FILE_FOLDER)
    total_files = len(files)

    total_size = 0
    largest_file = {
        "name": None,
        "size": 0
    }

    for photo in photos:
        path = os.path.join(PHOTO_FOLDER, photo.saved_filename)

        if os.path.exists(path):
            size = os.path.getsize(path)
            total_size += size

            if size > largest_file["size"]:
                largest_file = {
                    "name": photo.saved_filename,
                    "size": size
                }

    for filename in files:
        path = os.path.join(FILE_FOLDER, filename)

        if os.path.exists(path):
            size = os.path.getsize(path)
            total_size += size

            if size > largest_file["size"]:
                largest_file = {
                    "name": filename,
                    "size": size
                }

    return {
        "total_photos": total_photos,
        "total_files": total_files,
        "total_size": total_size,
        "largest_file": largest_file
    }