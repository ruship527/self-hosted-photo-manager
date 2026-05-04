from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String)
    saved_filename = Column(String)
    taken_date = Column(String)
    upload_date = Column(String)
    file_hash = Column(String, unique=True)
    tags = Column(String)
    album = Column(String, default="Unsorted")

    albums = relationship("AlbumPhoto", back_populates="photo")


class Album(Base):
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    photos = relationship("AlbumPhoto", back_populates="album", cascade="all, delete")


class AlbumPhoto(Base):
    __tablename__ = "album_photos"

    id = Column(Integer, primary_key=True, index=True)
    album_id = Column(Integer, ForeignKey("albums.id"))
    photo_id = Column(Integer, ForeignKey("photos.id"))

    album = relationship("Album", back_populates="photos")
    photo = relationship("Photo", back_populates="albums")