import os
from app.database import SessionLocal
from app.models import Photo
from app.utils import PHOTO_FOLDER, generate_ai_tags

db = SessionLocal()

photos = db.query(Photo).all()

for photo in photos:
    path = os.path.join(PHOTO_FOLDER, photo.saved_filename)

    if not os.path.exists(path):
        print(f"Missing file: {photo.saved_filename}")
        continue

    print(f"Tagging: {photo.saved_filename}")
    tags = generate_ai_tags(path)
    photo.tags = tags
    print(f" -> {tags}")

db.commit()
db.close()

print("Done.")
