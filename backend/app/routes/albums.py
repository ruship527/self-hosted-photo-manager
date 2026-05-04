import os
from app.database import SessionLocal
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Album, AlbumPhoto, Photo
from app.routes.auth import authenticate
from app.utils import BASE_DIR

from fastapi.templating import Jinja2Templates
from fastapi import Request

router = APIRouter(tags=["Albums"])

templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "frontend")
)

@router.get("/albums")
def albums_page(request: Request, db: Session = Depends(get_db)):
    albums = db.query(Album).all()

    return templates.TemplateResponse(
        request,
        "albums.html",
        {
            "albums": albums
        }
    )

@router.get("/albums/data")
def get_albums(db: Session = Depends(get_db)):
    return db.query(Album).all()

@router.post("/albums/create")
def create_album(name: str = Form(...), db: Session = Depends(get_db)):
    album = Album(name=name)

    db.add(album)
    db.commit()
    db.refresh(album)

    return RedirectResponse(url="/albums", status_code=303)


@router.get("/albums/{album_id}")
def get_album(request: Request, album_id: int, db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    album_photos = (
        db.query(Photo)
        .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
        .filter(AlbumPhoto.album_id == album_id)
        .all()
    )

    all_photos = db.query(Photo).order_by(Photo.id.desc()).all()

    album_photo_ids = [photo.id for photo in album_photos]

    return templates.TemplateResponse(
        request,
        "album_detail.html",
        {
            "album": album,
            "album_photos": album_photos,
            "photos": all_photos,
            "album_photo_ids": album_photo_ids
        }
    )

@router.post("/albums/{album_id}/add/{photo_id}")
def add_photo_to_album(
    album_id: int,
    photo_id: int,
    db: Session = Depends(get_db)
):
    album = db.query(Album).filter(Album.id == album_id).first()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    existing = db.query(AlbumPhoto).filter(
        AlbumPhoto.album_id == album_id,
        AlbumPhoto.photo_id == photo_id
    ).first()

    if existing:
        return RedirectResponse(url=f"/albums/{album_id}", status_code=303)

    album_photo = AlbumPhoto(
        album_id=album_id,
        photo_id=photo_id
    )

    db.add(album_photo)
    db.commit()

    return RedirectResponse(url=f"/albums/{album_id}", status_code=303)


@router.delete("/albums/{album_id}/remove/{photo_id}")
def remove_photo_from_album(
    album_id: int,
    photo_id: int,
    db: Session = Depends(get_db)
):
    album_photo = db.query(AlbumPhoto).filter(
        AlbumPhoto.album_id == album_id,
        AlbumPhoto.photo_id == photo_id
    ).first()

    if not album_photo:
        raise HTTPException(status_code=404, detail="Photo not found in album")

    db.delete(album_photo)
    db.commit()

    return {"message": "Photo removed from album"}


@router.post("/albums/{album_id}/delete")
def delete_album(album_id: int, db: Session = Depends(get_db)):
    album = db.query(Album).filter(Album.id == album_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).delete()
    db.delete(album)
    db.commit()

    return RedirectResponse(url="/albums", status_code=303)