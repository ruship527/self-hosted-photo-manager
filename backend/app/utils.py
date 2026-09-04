import os
import uuid
import hashlib
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS
from transformers import BlipProcessor, BlipForConditionalGeneration

def build_filename(original_filename):
    ext = os.path.splitext(original_filename)[1].lower()
    unique_name = str(uuid.uuid4())
    return unique_name + ext

def get_photo_taken_date(image_path):
    try:
        image = Image.open(image_path)
        exif_data = image.getexif()

        if not exif_data:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)

            if tag == "DateTimeOriginal":
                return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/DATA/photoapp/uploads")
PHOTO_FOLDER = os.path.join(UPLOAD_FOLDER, "photos")
FILE_FOLDER = os.path.join(UPLOAD_FOLDER, "files")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)
os.makedirs(FILE_FOLDER, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Strip any path component / null bytes so a user-supplied filename
    can never escape the folder it's joined into."""
    name = os.path.basename((filename or "").replace("\x00", ""))

    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")

    return name


def safe_join(folder: str, filename: str) -> str:
    """os.path.join that refuses to resolve outside `folder`."""
    candidate = os.path.realpath(os.path.join(folder, sanitize_filename(filename)))
    folder_real = os.path.realpath(folder)

    if candidate != folder_real and not candidate.startswith(folder_real + os.sep):
        raise ValueError("Path escapes target folder")

    return candidate



caption_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
caption_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

def generate_ai_tags(image_path):
    try:
        image = Image.open(image_path).convert("RGB")

        inputs = caption_processor(image, return_tensors="pt")
        output = caption_model.generate(**inputs, max_new_tokens=30)

        caption = caption_processor.decode(output[0], skip_special_tokens=True).lower()

        words_to_remove = {
            "a", "an", "the", "and", "or", "of", "in", "on", "with",
            "is", "are", "there", "this", "that", "photo", "image",
            "picture", "showing", "from", "his", "her", "their", "out",
            "at", "to", "for", "by", "it", "its", "as"
        }

        words = caption.replace(",", "").replace(".", "").split()

        clean_words = []
        for word in words:
            if word not in words_to_remove and len(word) > 2:
                clean_words.append(word)

        tags = set(clean_words)

        clean_caption = " ".join(clean_words)
        if clean_caption:
            tags.add(clean_caption)

        return ", ".join(sorted(tags))

    except Exception as e:
        print(f"AI tagging failed: {e}")
        return ""