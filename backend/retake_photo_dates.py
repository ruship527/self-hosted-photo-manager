import os
from app.database import SessionLocal
from app.models import Photo
from app.utils import PHOTO_FOLDER, get_photo_taken_date

db = SessionLocal()

photos = db.query(Photo).all()
updated = 0

for photo in photos:
    path = os.path.join(PHOTO_FOLDER, photo.saved_filename)

    if not os.path.exists(path):
        print(f"Missing file: {photo.saved_filename}")
        continue

    # Falls back to the photo's own already-stored taken_date when there's
    # no real EXIF date, so photos with no metadata are left untouched
    # instead of getting overwritten with today's date (whenever this
    # script happens to run).
    new_date = get_photo_taken_date(path, fallback=photo.taken_date)

    if new_date != photo.taken_date:
        print(f"{photo.saved_filename}: {photo.taken_date} -> {new_date}")
        photo.taken_date = new_date
        updated += 1

db.commit()
db.close()

print(f"Done. Updated {updated} of {len(photos)} photos.")
