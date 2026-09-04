import logging
import os
import uuid
import hashlib
from datetime import datetime

from PIL import Image, ImageOps
from PIL.ExifTags import TAGS

logger = logging.getLogger("photoapp")


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
THUMBNAIL_FOLDER = os.path.join(UPLOAD_FOLDER, "thumbnails")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)
os.makedirs(FILE_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

THUMBNAIL_SIZE = (400, 400)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


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


def save_upload(file, dest_path: str, max_bytes: int = MAX_UPLOAD_BYTES) -> int:
    """Stream an UploadFile to disk, aborting (and cleaning up the partial
    file) if it exceeds max_bytes. Returns the number of bytes written."""
    written = 0

    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_SIZE)

                if not chunk:
                    break

                written += len(chunk)

                if written > max_bytes:
                    raise ValueError(f"File exceeds the {max_bytes} byte upload limit")

                buffer.write(chunk)
    except ValueError:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise

    return written


def is_valid_image(path: str) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def make_thumbnail(source_path: str, dest_path: str, size=THUMBNAIL_SIZE) -> None:
    """Generate a resized copy of an image for fast gallery loading.
    Applies the EXIF orientation tag before resizing so rotated phone
    photos come out right-side-up, then saves in the source's own format."""
    with Image.open(source_path) as img:
        fmt = img.format
        img = ImageOps.exif_transpose(img)
        img.thumbnail(size)

        tmp_path = dest_path + ".tmp"
        img.save(tmp_path, format=fmt)
        os.replace(tmp_path, dest_path)


# The BLIP captioning model is large and slow to load, so it's only
# imported/loaded the first time AI tagging is actually needed. This keeps
# app startup fast and lets this module be imported (e.g. in tests) without
# torch/transformers installed at all.
_caption_processor = None
_caption_model = None


def _get_captioner():
    global _caption_processor, _caption_model

    if _caption_processor is None or _caption_model is None:
        from transformers import BlipProcessor, BlipForConditionalGeneration

        _caption_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        _caption_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

    return _caption_processor, _caption_model


def generate_ai_tags(image_path):
    try:
        processor, model = _get_captioner()

        image = Image.open(image_path).convert("RGB")

        inputs = processor(image, return_tensors="pt")
        output = model.generate(**inputs, max_new_tokens=30)

        caption = processor.decode(output[0], skip_special_tokens=True).lower()

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

    except Exception:
        logger.exception("AI tagging failed for %s", image_path)
        return ""
