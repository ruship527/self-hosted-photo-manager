import os
from urllib.parse import quote

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


def _exact_name_ilike(column, name: str):
    """Case-insensitive *exact* match on `name` - ilike() treats a bare "%"
    or "_" in the value as a wildcard, so without escaping, creating an
    album named e.g. "50%" would report a false duplicate against any
    existing "50X" album (and vice versa)."""
    escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(escaped, escape="\\")

templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "frontend")
)

@router.get("/albums")
def albums_page(request: Request, search: str = "", error: str = "", db: Session = Depends(get_db), user: str = Depends(authenticate)):
    query = db.query(Album)

    if search:
        query = query.filter(Album.name.contains(search))

    albums = query.all()

    # A cover thumbnail + photo count per album, so the list isn't just
    # bare names - one extra query per album, but album counts are small
    # and this is a low-traffic personal page.
    album_cards = []

    for album in albums:
        first_photo = (
            db.query(Photo)
            .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .filter(AlbumPhoto.album_id == album.id)
            .order_by(Photo.id.desc())
            .first()
        )
        photo_count = (
            db.query(AlbumPhoto)
            .filter(AlbumPhoto.album_id == album.id)
            .count()
        )

        album_cards.append({
            "album": album,
            "cover": first_photo,
            "photo_count": photo_count,
        })

    return templates.TemplateResponse(
        request,
        "albums.html",
        {
            "album_cards": album_cards,
            "search": search,
            "error": error
        }
    )

@router.get("/albums/data")
def get_albums(db: Session = Depends(get_db), user: str = Depends(authenticate)):
    return db.query(Album).all()

@router.post("/albums/create")
def create_album(name: str = Form(...), db: Session = Depends(get_db), user: str = Depends(authenticate)):
    name = name.strip()

    if not name:
        return RedirectResponse(url="/albums?error=Album+name+can%27t+be+empty", status_code=303)

    existing = db.query(Album).filter(_exact_name_ilike(Album.name, name)).first()
    if existing:
        return RedirectResponse(
            url=f"/albums?error={quote(f'An album named {name!r} already exists')}",
            status_code=303
        )

    album = Album(name=name)

    db.add(album)
    db.commit()
    db.refresh(album)

    return RedirectResponse(url="/albums", status_code=303)


@router.post("/albums/{album_id}/rename")
def rename_album(
    album_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate)
):
    album = db.query(Album).filter(Album.id == album_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    name = name.strip()

    if not name:
        return RedirectResponse(url=f"/albums/{album_id}?error=Album+name+can%27t+be+empty", status_code=303)

    existing = db.query(Album).filter(_exact_name_ilike(Album.name, name), Album.id != album_id).first()
    if existing:
        return RedirectResponse(
            url=f"/albums/{album_id}?error={quote(f'An album named {name!r} already exists')}",
            status_code=303
        )

    album.name = name
    db.commit()

    return RedirectResponse(url=f"/albums/{album_id}", status_code=303)


@router.get("/albums/{album_id}")
def get_album(request: Request, album_id: int, error: str = "", db: Session = Depends(get_db), user: str = Depends(authenticate)):
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
            "album_photo_ids": album_photo_ids,
            "error": error
        }
    )

@router.post("/albums/{album_id}/add/{photo_id}")
def add_photo_to_album(
    album_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate)
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


@router.post("/albums/{album_id}/add-photos")
def add_photos_to_album(
    album_id: int,
    photo_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    user: str = Depends(authenticate)
):
    """Bulk version of add_photo_to_album - checks off any number of photos
    in the album-detail page's "Add photos" section and commits them all
    with one Save, instead of one request (and one page reload) per photo."""
    album = db.query(Album).filter(Album.id == album_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    if photo_ids:
        already_in_album = {
            row.photo_id for row in
            db.query(AlbumPhoto.photo_id).filter(
                AlbumPhoto.album_id == album_id,
                AlbumPhoto.photo_id.in_(photo_ids)
            )
        }

        valid_photo_ids = {
            row.id for row in
            db.query(Photo.id).filter(Photo.id.in_(photo_ids))
        }

        for photo_id in valid_photo_ids - already_in_album:
            db.add(AlbumPhoto(album_id=album_id, photo_id=photo_id))

        db.commit()

    return RedirectResponse(url=f"/albums/{album_id}", status_code=303)


@router.delete("/albums/{album_id}/remove/{photo_id}")
def remove_photo_from_album(
    album_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(authenticate)
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
def delete_album(album_id: int, db: Session = Depends(get_db), user: str = Depends(authenticate)):
    album = db.query(Album).filter(Album.id == album_id).first()

    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album_id).delete()
    db.delete(album)
    db.commit()

    return RedirectResponse(url="/albums", status_code=303)